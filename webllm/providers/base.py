from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from webllm.models import Source
from webllm.states import PageState

COMMON_INPUT_SELECTORS = (
    "textarea",
    "[contenteditable='true']",
    "div[role='textbox']",
)
COMMON_BUSY_SELECTORS = (
    "button[aria-label*='Stop']",
    "button[title*='Stop']",
    "button:has-text('Stop')",
    "button[aria-label*='停止']",
    "button[title*='停止']",
    "button:has-text('停止')",
    "button:has-text('停止生成')",
)
COMMON_ANSWER_SELECTORS = (
    "[data-type='assistant']",
    "[data-role='assistant']",
    "[data-message-role='assistant']",
    "[data-message-author-role='assistant']",
    "[class*='assistant-message']",
    "[class*='assistant_message']",
    "[class*='answer-content']",
)
COMMON_NEW_SESSION_SELECTORS = (
    "button:has-text('新会话')",
    "button:has-text('新聊天')",
    "button:has-text('新对话')",
    "button:has-text('新建对话')",
    "div.new-dialog-container-button:has-text('开启新对话')",
    "div.new-dialog-container-button:has-text('新对话')",
    "button[aria-label*='新会话']",
    "button[aria-label*='新聊天']",
    "button[aria-label*='新对话']",
    "button[aria-label*='New chat']",
    "button:has-text('New chat')",
    "button:has-text('New conversation')",
)
COMMON_SEND_BUTTON_SELECTORS = (
    "button[aria-label*='发送']",
    "button[title*='发送']",
    "button:has-text('发送')",
    "button[aria-label*='Send']",
    "button[title*='Send']",
    "button:has-text('Send')",
)
COMMON_COPY_BUTTON_SELECTORS = (
    "button[aria-label*='复制']",
    "[role='button'][aria-label*='复制']",
    "button[title*='复制']",
    "button:has-text('复制')",
    "button[aria-label*='Copy']",
    "[role='button'][aria-label*='Copy']",
    "button[title*='Copy']",
    "button:has-text('Copy')",
    "button[aria-label*='copy']",
    "[role='button'][aria-label*='copy']",
    "button[title*='copy']",
    "button[class*='copy-btn']",
    "[class*='copy-btn']",
)
COMMON_SOURCE_SELECTORS = (
    "[class*='citation'] a[href]",
    "[class*='reference'] a[href]",
    "[class*='source'] a[href]",
    "[class*='search-result'] a[href]",
    "[class*='search_result'] a[href]",
)
COMMON_LOGIN_URL_PATTERNS = (
    "/sign_in",
    "/signin",
    "/login",
    "passport",
    "wappass",
    "/auth",
)
COMMON_POPUP_SELECTORS = (
    "[role='dialog']",
    "[aria-modal='true']",
    "[class*='modal']",
    "[class*='popup']",
    "[class*='guide-mask']",
    "[class*='guide_mask']",
    "[class*='overlay']",
    "[class*='cookie-banner']",
    "[class*='privacy-banner']",
)
COMMON_POPUP_DISMISS_SELECTORS = (
    "button:has-text('关闭')",
    "[aria-label*='关闭']",
    "[title*='关闭']",
    "button:has-text('我知道了')",
    "button:has-text('知道了')",
    "button:has-text('以后再说')",
    "button:has-text('暂不')",
    "button:has-text('跳过')",
    "button:has-text('Skip')",
    "button:has-text('Close')",
    "[role='dialog'] [class*='close']",
    "[class*='close-btn']",
    "[class*='closeBtn']",
)


@dataclass(frozen=True)
class AnswerFingerprint:
    node_count: int
    last_text: str = ""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    url: str
    hostnames: tuple[str, ...]
    input_selectors: tuple[str, ...] = COMMON_INPUT_SELECTORS
    busy_selectors: tuple[str, ...] = COMMON_BUSY_SELECTORS
    answer_selectors: tuple[str, ...] = COMMON_ANSWER_SELECTORS
    new_session_selectors: tuple[str, ...] = COMMON_NEW_SESSION_SELECTORS
    send_button_selectors: tuple[str, ...] = COMMON_SEND_BUTTON_SELECTORS
    copy_button_selectors: tuple[str, ...] = COMMON_COPY_BUTTON_SELECTORS
    source_selectors: tuple[str, ...] = COMMON_SOURCE_SELECTORS
    source_scope_selectors: tuple[str, ...] = ()
    source_item_selectors: tuple[str, ...] = ()
    file_input_selectors: tuple[str, ...] = ()
    response_idle_ms: float = 2500
    supports_new_session: bool = True
    supports_sources: bool = True
    login_url_patterns: tuple[str, ...] = COMMON_LOGIN_URL_PATTERNS
    login_selectors: tuple[str, ...] = ()
    captcha_selectors: tuple[str, ...] = ()
    rate_limit_selectors: tuple[str, ...] = ()
    maintenance_selectors: tuple[str, ...] = ()
    popup_selectors: tuple[str, ...] = COMMON_POPUP_SELECTORS
    popup_dismiss_selectors: tuple[str, ...] = COMMON_POPUP_DISMISS_SELECTORS
    dynamic_selectors: tuple[str, ...] = ()
    ui_diff_threshold: float = 0.03


@dataclass(frozen=True)
class Capture:
    text: str
    mode: str


class WebProvider:
    """Base adapter for one LLM web UI.

    Provider-specific modules override selectors through ``spec`` and can
    override any method (for example ``extract_sources``) when a site needs
    different behaviour.
    """

    spec: ProviderSpec

    def find_input(self, page: Page, timeout: float = 30000):
        """Wait for the composer, retrying while the page restores the login session."""
        deadline = time.monotonic() + timeout / 1000
        while True:
            for selector in self.spec.input_selectors:
                remaining_ms = (deadline - time.monotonic()) * 1000
                if remaining_ms <= 0:
                    break
                locator = page.locator(selector).first
                try:
                    locator.wait_for(state="visible", timeout=min(3000, remaining_ms))
                    return locator
                except PlaywrightError:
                    continue
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Could not find the {self.spec.display_name} message input box "
                    f"within {timeout / 1000:.0f} seconds. "
                    "Make sure the browser is logged in and the chat page is open."
                )
            time.sleep(0.5)

    def detect_state(self, page: Page, probe_timeout: float = 1500) -> PageState:
        try:
            url = (page.url or "").lower()
        except PlaywrightError:
            url = ""

        for pattern in self.spec.login_url_patterns:
            if pattern.lower() in url:
                return PageState.LOGGED_OUT

        if self._any_visible(page, self.spec.captcha_selectors):
            return PageState.CAPTCHA
        if self._any_visible(page, self.spec.rate_limit_selectors):
            return PageState.RATE_LIMITED
        if self._any_visible(page, self.spec.maintenance_selectors):
            return PageState.MAINTENANCE
        if self._any_visible(page, self.spec.login_selectors):
            return PageState.LOGGED_OUT
        if self._any_visible(page, self.spec.input_selectors, probe_timeout):
            return PageState.READY
        return PageState.LOADING

    def answer_fingerprint(self, page: Page) -> AnswerFingerprint:
        for selector in self.spec.answer_selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except PlaywrightError:
                continue
            if count == 0:
                continue
            try:
                text = (locator.last.inner_text(timeout=1000) or "").strip()
            except PlaywrightError:
                text = ""
            return AnswerFingerprint(node_count=count, last_text=text)
        return AnswerFingerprint(node_count=0)

    def wait_for_answer_start(
        self,
        page: Page,
        previous: AnswerFingerprint,
        timeout: float,
        poll_ms: float = 250,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.answer_fingerprint(page)
            if current.node_count > previous.node_count:
                return True
            if current.last_text and current.last_text != previous.last_text:
                return True
            page.wait_for_timeout(poll_ms)
        return False

    def find_popups(self, page: Page):
        from webllm.diagnostics import find_popups

        return find_popups(page, self.spec.popup_selectors)

    def dismiss_popups(self, page: Page) -> int:
        from webllm.diagnostics import dismiss_popups

        return dismiss_popups(page, self.spec.popup_dismiss_selectors)

    @staticmethod
    def _any_visible(page: Page, selectors: tuple[str, ...], timeout: float = 0) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible():
                    return True
            except PlaywrightError:
                continue
            if timeout:
                try:
                    locator.wait_for(state="visible", timeout=min(1000, timeout))
                    return True
                except PlaywrightError:
                    continue
        return False

    def prepare_for_question(self, page: Page) -> None:
        """Provider hook run right before each question is submitted.

        Default is a no-op; providers override it for per-question setup such
        as enabling a provider-specific toggle.
        """
        return None

    def select_mode(self, page: Page, mode: str) -> None:
        """Provider hook to switch a conversation mode.

        Only called when a mode is requested and a new session was just started
        (some sites only allow switching mode on the new-chat screen). Default
        is a no-op; providers that support modes override it.
        """
        raise RuntimeError(f"{self.spec.display_name} does not support selecting a mode.")

    def attach_files(self, page: Page, paths: list[str]) -> None:
        """Attach local files to the composer before submitting.

        The default implementation sets ``spec.file_input_selectors`` (a hidden
        ``<input type=file>`` is fine). Providers without an upload input raise.
        """
        if not self.spec.file_input_selectors:
            raise RuntimeError(f"{self.spec.display_name} does not support file upload.")

        missing = [path for path in paths if not Path(path).is_file()]
        if missing:
            raise ValueError(f"Attachment not found: {missing[0]}")

        last_error: Exception | None = None
        for selector in self.spec.file_input_selectors:
            locator = page.locator(selector).first
            try:
                if locator.count() == 0:
                    continue
                locator.set_input_files(list(paths), timeout=10000)
                return
            except PlaywrightError as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise RuntimeError(
                f"Could not upload attachment for {self.spec.display_name}: {last_error}"
            ) from last_error
        raise RuntimeError(f"Could not find the {self.spec.display_name} file input.")

    def submit(self, page: Page, question: str) -> None:
        message_input = self.find_input(page)
        message_input.click()
        message_input.press("Control+a")
        message_input.press("Delete")
        message_input.type(question, delay=20)
        if self._read_input_text(message_input) != question:
            message_input.fill(question)
        message_input.press("Enter")
        if self._input_still_contains(message_input, question, timeout_ms=4000):
            self._click_send_button(page)

    def wait_for_complete(self, page: Page, timeout: float, idle_ms: float | None = None) -> None:
        timeout_ms = timeout * 1000
        idle_ms = self.spec.response_idle_ms if idle_ms is None else idle_ms
        saw_busy_indicator = False

        for selector in self.spec.busy_selectors:
            busy_indicator = page.locator(selector).last
            try:
                busy_indicator.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeoutError:
                continue

            saw_busy_indicator = True
            try:
                busy_indicator.wait_for(state="hidden", timeout=timeout_ms)
                break
            except PlaywrightTimeoutError:
                raise RuntimeError(
                    f"Timed out waiting for {self.spec.display_name} response "
                    f"to finish after {timeout} seconds."
                ) from None

        if not saw_busy_indicator:
            self._wait_for_dom_idle(page, timeout, idle_ms)

        self.find_input(page)

    def capture_answer(self, page: Page) -> Capture:
        bubble = self._find_answer_bubble(page)
        if bubble is not None:
            try:
                bubble.hover(timeout=2000)
            except PlaywrightError:
                pass
        copy_button = self._find_copy_button(page, bubble)

        if copy_button is not None:
            sentinel = f"__webllm_clipboard_{uuid.uuid4().hex}__"
            self._write_clipboard(page, sentinel)
            try:
                copy_button.click(timeout=2000)
            except PlaywrightError:
                pass
            else:
                page.wait_for_timeout(300)
                text = self._read_clipboard_text(page, ignore=sentinel)
                if text:
                    return Capture(text, "copy")

        if bubble is not None:
            try:
                text = (bubble.inner_text(timeout=3000) or "").strip()
            except PlaywrightError:
                text = ""
            if text:
                return Capture(text, "text")

        return Capture("", "none")

    def extract_sources(self, page: Page) -> list[Source]:
        if not self.spec.supports_sources:
            return []

        scope = self._find_source_scope(page)
        if scope is None:
            return []

        sources: list[Source] = []
        seen: set[str] = set()

        for selector in self.spec.source_selectors:
            for element in self._iter_locator(scope.locator(selector)):
                self._collect_source(sources, seen, page, element, kind="citation")

        for selector in self.spec.source_item_selectors:
            for element in self._iter_locator(scope.locator(selector)):
                self._collect_source(sources, seen, page, element, kind="citation")

        for anchor in self._iter_locator(scope.locator("a[href]")):
            self._collect_source(sources, seen, page, anchor, kind="link")

        return sources

    def start_new_session(self, page: Page) -> None:
        if not self.spec.supports_new_session:
            raise RuntimeError(f"{self.spec.display_name} does not support starting a new session.")

        for selector in self.spec.new_session_selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=3000)
                locator.click()
                self.find_input(page)
                return
            except PlaywrightError:
                continue
        raise RuntimeError(f"Could not find the {self.spec.display_name} new session button.")

    def _find_answer_bubble(self, page: Page):
        return self._find_last(page, self.spec.answer_selectors)

    def _find_source_scope(self, page: Page):
        selectors = self.spec.source_scope_selectors or self.spec.answer_selectors
        scope = self._find_last(page, selectors)
        return scope if scope is not None else self._find_answer_bubble(page)

    @staticmethod
    def _find_last(page: Page, selectors: tuple[str, ...]):
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count() == 0:
                    continue
                return locator.last
            except PlaywrightError:
                continue
        return None

    def _find_copy_button(self, page: Page, answer_bubble=None):
        scopes = [answer_bubble, page] if answer_bubble is not None else [page]
        for scope in scopes:
            for selector in self.spec.copy_button_selectors:
                try:
                    candidate = scope.locator(selector).last
                    candidate.wait_for(state="visible", timeout=1000)
                except PlaywrightError:
                    continue
                return candidate
        return None

    def _click_send_button(self, page: Page) -> None:
        for selector in self.spec.send_button_selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=1500)
                locator.click()
                return
            except PlaywrightError:
                continue
        raise RuntimeError("Enter did not submit the question and no send button was found.")

    @staticmethod
    def _read_input_text(message_input, timeout_ms: float = 2000) -> str | None:
        for read in (message_input.input_value, message_input.inner_text):
            try:
                return (read(timeout=timeout_ms) or "").strip()
            except PlaywrightError:
                continue
        return None

    def _input_still_contains(self, message_input, question: str, timeout_ms: float) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            text = self._read_input_text(message_input, timeout_ms=500)
            if text is None or question not in text:
                return False
            time.sleep(0.2)
        return True

    @staticmethod
    def _iter_locator(locator) -> Iterator[object]:
        try:
            count = locator.count()
        except PlaywrightError:
            return
        for index in range(count):
            try:
                yield locator.nth(index)
            except PlaywrightError:
                continue

    def _collect_source(
        self,
        sources: list[Source],
        seen: set[str],
        page: Page,
        element,
        kind: str,
    ) -> None:
        try:
            source = self._build_source(page, element, kind)
        except Exception:
            return
        if source is None or source.url in seen:
            return
        seen.add(source.url)
        sources.append(source)

    def _build_source(self, page: Page, element, kind: str) -> Source | None:
        href = self._element_href(element)
        if not href:
            return None

        url = self._normalize_source_url(page, href)
        if url is None:
            return None

        title = self._element_text(element)
        return Source(
            url=url,
            title=title[:300],
            snippet=title[:500],
            kind=kind,
        )

    @staticmethod
    def _element_href(element) -> str:
        try:
            href = element.get_attribute("href")
        except PlaywrightError:
            return ""
        if href:
            return href

        try:
            links = element.locator("a[href]")
            if links.count() == 0:
                return ""
            return links.last.get_attribute("href") or ""
        except PlaywrightError:
            return ""

    @staticmethod
    def _element_text(element) -> str:
        try:
            return (element.inner_text(timeout=1000) or "").strip()
        except PlaywrightError:
            return ""

    def _normalize_source_url(self, page: Page, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "data:")):
            return None

        try:
            url = urljoin(page.url, href)
        except Exception:
            return None
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return None
        if self._is_internal_host(parts.hostname):
            return None
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

    def _is_internal_host(self, hostname: str | None) -> bool:
        if not hostname:
            return False
        hostname = hostname.lower()
        return any(
            hostname == candidate or hostname.endswith(f".{candidate}")
            for candidate in self.spec.hostnames
        )

    @staticmethod
    def _wait_for_dom_idle(page: Page, timeout: float, idle_ms: float) -> None:
        page.evaluate(
            """
            () => {
                const state = window.__webllmIdleState;
                if (state && state.observer) {
                    state.observer.disconnect();
                }
                delete window.__webllmIdleState;
            }
            """
        )
        page.wait_for_function(
            """
            ([idleMs]) => {
                const state = window.__webllmIdleState;
                const now = Date.now();

                if (!state) {
                    window.__webllmIdleState = {
                        lastMutationAt: now,
                        observer: new MutationObserver(() => {
                            window.__webllmIdleState.lastMutationAt = Date.now();
                        }),
                    };
                    window.__webllmIdleState.observer.observe(document.body, {
                        childList: true,
                        subtree: true,
                        characterData: true,
                    });
                    return false;
                }

                return now - state.lastMutationAt >= idleMs;
            }
            """,
            arg=[idle_ms],
            timeout=timeout * 1000,
        )

    @staticmethod
    def _ensure_clipboard_permissions(page: Page) -> None:
        grant_kwargs: dict[str, str] = {}
        try:
            parts = urlsplit(page.url)
            if parts.scheme and parts.netloc:
                grant_kwargs["origin"] = f"{parts.scheme}://{parts.netloc}"
        except PlaywrightError:
            pass
        try:
            page.context.grant_permissions(["clipboard-read", "clipboard-write"], **grant_kwargs)
        except PlaywrightError:
            pass

    def _write_clipboard(self, page: Page, text: str) -> None:
        try:
            self._ensure_clipboard_permissions(page)
            page.evaluate("(text) => navigator.clipboard.writeText(text)", text)
        except Exception:
            pass

    @staticmethod
    def _read_clipboard_once(page: Page) -> str | None:
        try:
            cdp_session = page.context.new_cdp_session(page)
            try:
                text = cdp_session.send("Clipboard.readText").get("text")
            finally:
                cdp_session.detach()
        except PlaywrightError:
            text = None
        if text and text.strip():
            return text.strip()

        try:
            text = page.evaluate("() => navigator.clipboard.readText()")
        except PlaywrightError:
            return None
        if text and text.strip():
            return text.strip()
        return None

    def _read_clipboard_text(
        self, page: Page, timeout: float = 2.0, ignore: str | None = None
    ) -> str | None:
        self._ensure_clipboard_permissions(page)
        deadline = time.monotonic() + timeout
        while True:
            text = self._read_clipboard_once(page)
            if text and text != ignore:
                return text
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.25)
