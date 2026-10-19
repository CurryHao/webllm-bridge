from __future__ import annotations

from webllm.browser import BrowserSession
from webllm.providers.deepseek import DeepSeekProvider


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.front = False
        self.closed = False
        self.goto_calls: list[tuple[str, str]] = []

    def bring_to_front(self) -> None:
        self.front = True

    def goto(self, url: str, wait_until: str) -> None:
        self.url = url
        self.goto_calls.append((url, wait_until))

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, pages: list[FakePage] | None = None) -> None:
        self.pages = list(pages or [])

    def new_page(self) -> FakePage:
        page = FakePage("about:blank")
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self, contexts: list[FakeContext]) -> None:
        self.contexts = contexts

    def new_context(self) -> FakeContext:
        context = FakeContext()
        self.contexts.append(context)
        return context


def test_matches_spec_accepts_exact_host_and_subdomains() -> None:
    spec = DeepSeekProvider.spec

    assert BrowserSession._matches_spec("https://chat.deepseek.com/a/chat/1", spec) is True
    assert BrowserSession._matches_spec("https://deepseek.com/", spec) is True
    assert BrowserSession._matches_spec("https://www.deepseek.com/", spec) is True
    assert BrowserSession._matches_spec("https://example.com/", spec) is False


def test_acquire_page_reuses_existing_provider_tab() -> None:
    page = FakePage("https://chat.deepseek.com/a/chat/1")
    session = BrowserSession("http://127.0.0.1:9222")
    session._browser = FakeBrowser([FakeContext([page])])

    acquired = session.acquire_page(DeepSeekProvider.spec)

    assert acquired is page
    assert page.front is True
    assert page.goto_calls == []


def test_acquire_page_prefers_exact_host_over_other_subdomain() -> None:
    platform = FakePage("https://platform.deepseek.com/")
    chat = FakePage("https://chat.deepseek.com/a/chat/1")
    session = BrowserSession("http://127.0.0.1:9222")
    session._browser = FakeBrowser([FakeContext([platform, chat])])

    acquired = session.acquire_page(DeepSeekProvider.spec)

    assert acquired is chat


def test_acquire_page_opens_tab_when_provider_is_not_open() -> None:
    session = BrowserSession("http://127.0.0.1:9222")
    session._browser = FakeBrowser([FakeContext()])

    page = session.acquire_page(DeepSeekProvider.spec)

    assert page.url == "https://chat.deepseek.com/"
    assert page.goto_calls == [("https://chat.deepseek.com/", "domcontentloaded")]
    assert session.page_url("deepseek") == "https://chat.deepseek.com/"


def test_close_created_pages_does_not_close_reused_tabs() -> None:
    existing = FakePage("https://chat.deepseek.com/a/chat/1")
    session = BrowserSession("http://127.0.0.1:9222")
    session._browser = FakeBrowser([FakeContext([existing])])
    session.acquire_page(DeepSeekProvider.spec)

    session.close_created_pages()

    assert existing.closed is False
