from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace

from webllm.browser import BrowserSession
from webllm.diagnostics import (
    HealthCheckConfig,
    PageHealthReport,
    capture_evidence,
    check_ready,
    run_page_health,
)
from webllm.errors import WebLLMError
from webllm.input import is_session_break_marker
from webllm.models import Answer, BatchResult, Source
from webllm.providers import get_provider
from webllm.states import NEEDS_HUMAN_STATES, STATE_ERROR_CODES, PageState


@dataclass
class AskOptions:
    timeout: float = 300.0
    delay: float = 0.0
    capture_sources: bool = True
    new_session: bool = False
    mode: str | None = None
    attachments: list[str] = field(default_factory=list)
    response_idle_ms: float | None = None
    close_pages: bool = False
    stop_on_error: bool = True
    preflight: bool = True
    preflight_timeout: float = 30.0
    wait_human: float = 0.0
    require_answer_change: bool = True
    health: HealthCheckConfig | None = None


class WebLLMClient:
    """Reusable, agent-oriented client for LLM web UIs.

    One client keeps one CDP connection and one tab per provider, so repeated
    calls reuse the same logged-in conversation.
    """

    def __init__(
        self,
        cdp_url: str,
        *,
        connection_timeout_ms: float = 30000,
        health: HealthCheckConfig | None = None,
    ) -> None:
        self.cdp_url = cdp_url
        self.connection_timeout_ms = connection_timeout_ms
        self._session: BrowserSession | None = None
        self._options = AskOptions(health=health)
        self._checked: dict[str, PageHealthReport] = {}

    def __enter__(self) -> "WebLLMClient":
        self._session = BrowserSession(self.cdp_url, self.connection_timeout_ms)
        self._session.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._session is None:
            return
        try:
            if self._options.close_pages:
                self._session.close_created_pages()
        finally:
            self._session.__exit__(*args)
            self._session = None

    def check(self, provider_name: str) -> PageHealthReport:
        provider = get_provider(provider_name)
        page = self._require_session().acquire_page(provider.spec)
        return self._ensure_health(provider, page, force=True)

    def ask(
        self,
        provider_name: str,
        question: str,
        *,
        timeout: float = 300.0,
        delay: float = 0.0,
        capture_sources: bool = True,
        new_session: bool = False,
        response_idle_ms: float | None = None,
        preflight: bool | None = None,
        options: AskOptions | None = None,
    ) -> Answer:
        options = options or self._options
        provider = get_provider(provider_name)
        page = self._require_session().acquire_page(provider.spec)
        started_at = time.monotonic()
        warnings: list[str] = []
        diagnostics: dict[str, object] = {}

        run_preflight = options.preflight if preflight is None else preflight
        if run_preflight:
            report = self._ensure_health(provider, page, options=options)
            if report is not None:
                warnings.extend(report.warnings)
                diagnostics["health"] = report.to_dict()

        if options.mode:
            new_session = True

        if new_session:
            provider.start_new_session(page)
            if options.mode:
                provider.select_mode(page, options.mode)

        if options.attachments:
            provider.attach_files(page, options.attachments)

        provider.prepare_for_question(page)

        previous = provider.answer_fingerprint(page) if options.require_answer_change else None
        provider.submit(page, question)

        if previous is not None:
            start_timeout = min(timeout, 90.0)
            if not provider.wait_for_answer_start(page, previous, timeout=start_timeout):
                screenshot = capture_evidence(
                    page,
                    self._health(options).screenshots_dir,
                    provider.spec.name,
                    "no-answer",
                )
                raise WebLLMError(
                    "answer_not_detected",
                    f"No new {provider.spec.display_name} answer appeared after submitting the question.",
                    retryable=True,
                    screenshot=screenshot,
                    diagnostics=diagnostics,
                )

        provider.wait_for_complete(page, timeout, idle_ms=response_idle_ms)

        capture = provider.capture_answer(page)
        if not capture.text:
            warnings.append("Answer text could not be captured from the page.")

        sources: list[Source] = []
        if capture_sources:
            try:
                sources = provider.extract_sources(page)
            except Exception as exc:
                warnings.append(f"Source extraction failed: {type(exc).__name__}: {exc}")

        if delay > 0:
            page.wait_for_timeout(delay * 1000)

        return Answer(
            provider=provider.spec.name,
            question=question,
            answer=capture.text,
            sources=sources,
            session_url=page.url,
            elapsed_seconds=time.monotonic() - started_at,
            captured_by=capture.mode,
            new_session=new_session,
            warnings=warnings,
            diagnostics=diagnostics,
        )

    def ask_many(
        self,
        provider_name: str,
        questions: list[str],
        *,
        options: AskOptions | None = None,
    ) -> BatchResult:
        options = options or self._options
        self._options = options
        provider = get_provider(provider_name)
        started_at = time.monotonic()
        results: list[Answer] = []
        pending_new_session = options.new_session or bool(options.mode)
        plain_options = (
            replace(options, mode=None, attachments=[])
            if (options.mode or options.attachments)
            else options
        )
        first_question = True

        for question in questions:
            if is_session_break_marker(question):
                pending_new_session = True
                continue

            call_options = (
                options if (pending_new_session or first_question) else plain_options
            )
            first_question = False
            question_started_at = time.monotonic()
            try:
                answer = self.ask(
                    provider_name,
                    question,
                    timeout=options.timeout,
                    delay=options.delay,
                    capture_sources=options.capture_sources,
                    new_session=pending_new_session,
                    response_idle_ms=options.response_idle_ms,
                    options=call_options,
                )
                pending_new_session = False
                results.append(answer)
            except WebLLMError as exc:
                results.append(
                    Answer(
                        provider=provider.spec.name,
                        question=question,
                        session_url=self._session.page_url(provider_name) if self._session else "",
                        elapsed_seconds=time.monotonic() - question_started_at,
                        new_session=pending_new_session,
                        error=f"{type(exc).__name__}: {exc}",
                        error_code=exc.code,
                        diagnostics=exc.diagnostics,
                    )
                )
                if options.stop_on_error:
                    break
            except Exception as exc:
                results.append(
                    Answer(
                        provider=provider.spec.name,
                        question=question,
                        session_url=self._session.page_url(provider_name) if self._session else "",
                        elapsed_seconds=time.monotonic() - question_started_at,
                        new_session=pending_new_session,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                if options.stop_on_error:
                    break

        return BatchResult(
            provider=provider.spec.name,
            display_name=provider.spec.display_name,
            results=results,
            session_url=self._session.page_url(provider_name) if self._session else "",
            elapsed_seconds=time.monotonic() - started_at,
        )

    def _ensure_health(
        self,
        provider,
        page,
        *,
        options: AskOptions | None = None,
        force: bool = False,
    ) -> PageHealthReport | None:
        options = options or self._options
        name = provider.spec.name
        if not force and name in self._checked:
            return self._checked[name]

        health = self._health(options)
        state, screenshot = check_ready(
            provider,
            page,
            timeout=options.preflight_timeout,
            wait_human=options.wait_human,
            screenshot_dir=health.screenshots_dir,
        )

        report = run_page_health(provider, page, health, state)
        if screenshot:
            report.screenshots.append(screenshot)

        if state in NEEDS_HUMAN_STATES or state is not PageState.READY:
            code = STATE_ERROR_CODES.get(state, "page_not_ready")
            report.blocking_code = code
            raise WebLLMError(
                code,
                f"{provider.spec.display_name} is not ready ({state.value}).",
                state=state,
                screenshot=screenshot,
                diagnostics=report.to_dict(),
            )

        if report.blocking_code:
            raise WebLLMError(
                report.blocking_code,
                f"{provider.spec.display_name} page health check failed: {report.blocking_code}.",
                state=state,
                diagnostics=report.to_dict(),
            )

        self._checked[name] = report
        return report

    def _health(self, options: AskOptions) -> HealthCheckConfig:
        return options.health or HealthCheckConfig()

    def _require_session(self) -> BrowserSession:
        if self._session is None:
            raise RuntimeError("WebLLMClient must be used as a context manager.")
        return self._session


def ask(
    provider_name: str,
    question: str,
    *,
    cdp_url: str | None = None,
    timeout: float = 300.0,
    delay: float = 0.0,
    capture_sources: bool = True,
    new_session: bool = False,
    mode: str | None = None,
    attachments: list[str] | None = None,
    preflight: bool = True,
    health: HealthCheckConfig | None = None,
) -> Answer:
    cdp_url = cdp_url or os.environ.get("WEBLLM_CDP_URL", "http://127.0.0.1:9222")
    options = AskOptions(
        timeout=timeout,
        delay=delay,
        capture_sources=capture_sources,
        new_session=new_session,
        mode=mode,
        attachments=list(attachments or []),
        preflight=preflight,
        health=health,
    )
    with WebLLMClient(cdp_url, health=health) as client:
        return client.ask(provider_name, question, options=options)
