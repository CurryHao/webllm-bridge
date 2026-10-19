from __future__ import annotations

import pytest

from webllm import service
from webllm.diagnostics import PageHealthReport
from webllm.models import Source
from webllm.providers.base import AnswerFingerprint, Capture
from webllm.service import AskOptions, WebLLMClient
from webllm.states import PageState


class FakeSpec:
    name = "deepseek"
    display_name = "DeepSeek"


class FakePage:
    url = "https://chat.deepseek.com/a/chat/1"

    def wait_for_timeout(self, timeout: float) -> None:
        return None


class FakeProvider:
    spec = FakeSpec()

    def __init__(self) -> None:
        self.events: list[str] = []
        self.fail_on: set[str] = set()
        self.prepared: list[object] = []

    def detect_state(self, page, probe_timeout: float = 1500):
        return PageState.READY

    def answer_fingerprint(self, page) -> AnswerFingerprint:
        return AnswerFingerprint(node_count=0)

    def wait_for_answer_start(self, page, previous, timeout: float, poll_ms: float = 250) -> bool:
        return True

    def start_new_session(self, page) -> None:
        self.events.append("new_session")

    def prepare_for_question(self, page) -> None:
        self.prepared.append(page)

    def select_mode(self, page, mode: str) -> None:
        self.events.append(f"mode:{mode}")

    def attach_files(self, page, paths) -> None:
        self.events.append(f"attach:{','.join(paths)}")

    def submit(self, page, question: str) -> None:
        self.events.append(f"submit:{question}")
        if question in self.fail_on:
            raise RuntimeError("submit failed")

    def wait_for_complete(self, page, timeout: float, idle_ms=None) -> None:
        self.events.append(f"wait:{timeout}")

    def capture_answer(self, page) -> Capture:
        return Capture(f"answer for {self.events[-1]}", "copy")

    def extract_sources(self, page) -> list[Source]:
        return [Source(url="https://example.com/source", title="Source")]


class FakeSession:
    def __init__(self) -> None:
        self.page = FakePage()
        self.closed = False
        self.closed_created = False

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.closed = True

    def acquire_page(self, spec):
        return self.page

    def page_url(self, provider_name: str) -> str:
        return self.page.url

    def close_created_pages(self) -> None:
        self.closed_created = True


@pytest.fixture
def fake_provider_and_session(monkeypatch):
    provider = FakeProvider()
    session = FakeSession()
    monkeypatch.setattr(service, "get_provider", lambda name: provider)
    monkeypatch.setattr(service, "BrowserSession", lambda cdp_url, timeout_ms: session)
    monkeypatch.setattr(
        service,
        "check_ready",
        lambda provider, page, timeout, wait_human, screenshot_dir: (PageState.READY, None),
    )
    monkeypatch.setattr(
        service,
        "run_page_health",
        lambda provider, page, config, state: PageHealthReport(
            provider=provider.spec.name, state=state
        ),
    )
    return provider, session


def test_ask_returns_answer_and_sources(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        answer = client.ask("deepseek", "question", timeout=30)

    assert answer.ok is True
    assert answer.answer == "answer for wait:30"
    assert answer.captured_by == "copy"
    assert answer.sources[0].url == "https://example.com/source"
    assert provider.events == ["submit:question", "wait:30"]


def test_ask_mode_forces_new_session_and_selects_mode(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        answer = client.ask(
            "deepseek", "question", timeout=30, options=AskOptions(mode="deep_search")
        )

    assert answer.new_session is True
    assert provider.events == ["new_session", "mode:deep_search", "submit:question", "wait:30"]


def test_ask_many_selects_mode_only_for_new_session(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        result = client.ask_many(
            "deepseek",
            ["question one", "question two"],
            options=AskOptions(timeout=10, mode="report"),
        )

    assert provider.events == [
        "new_session",
        "mode:report",
        "submit:question one",
        "wait:10",
        "submit:question two",
        "wait:10",
    ]
    assert [answer.new_session for answer in result.results] == [True, False]


def test_ask_attaches_files_before_submit(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        client.ask(
            "deepseek",
            "question",
            timeout=30,
            options=AskOptions(attachments=[r"C:\tmp\report.png"]),
        )

    assert provider.events == ["attach:C:\\tmp\\report.png", "submit:question", "wait:30"]


def test_ask_runs_provider_prepare_before_submit(fake_provider_and_session) -> None:
    provider, session = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        client.ask("deepseek", "question", timeout=30)

    assert provider.prepared == [session.page]


def test_ask_many_starts_new_session_after_marker(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        result = client.ask_many(
            "deepseek",
            ["question one", "__new_session__", "question two"],
            options=AskOptions(timeout=10),
        )

    assert result.ok is True
    assert provider.events == [
        "submit:question one",
        "wait:10",
        "new_session",
        "submit:question two",
        "wait:10",
    ]
    assert [answer.new_session for answer in result.results] == [False, True]


def test_ask_many_records_error_and_stops_by_default(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session
    provider.fail_on = {"question two"}

    with WebLLMClient("http://127.0.0.1:9222") as client:
        result = client.ask_many(
            "deepseek",
            ["question one", "question two", "question three"],
            options=AskOptions(timeout=10),
        )

    assert result.ok is False
    assert [answer.ok for answer in result.results] == [True, False]
    assert "submit failed" in (result.results[1].error or "")
    assert "submit:question three" not in provider.events


def test_ask_many_can_continue_after_error(fake_provider_and_session) -> None:
    provider, _ = fake_provider_and_session
    provider.fail_on = {"question two"}

    with WebLLMClient("http://127.0.0.1:9222") as client:
        result = client.ask_many(
            "deepseek",
            ["question one", "question two", "question three"],
            options=AskOptions(timeout=10, stop_on_error=False),
        )

    assert [answer.ok for answer in result.results] == [True, False, True]
    assert "submit:question three" in provider.events


def test_close_pages_option_is_forwarded(fake_provider_and_session) -> None:
    _, session = fake_provider_and_session

    with WebLLMClient("http://127.0.0.1:9222") as client:
        client.ask_many("deepseek", ["question"], options=AskOptions(close_pages=True))

    assert session.closed_created is True
