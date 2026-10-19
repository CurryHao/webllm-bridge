from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from webllm.providers import get_provider
from webllm.states import PageState


class FakeLocator:
    def __init__(self, visible: bool) -> None:
        self.visible = visible

    @property
    def first(self) -> "FakeLocator":
        return self

    def is_visible(self) -> bool:
        return self.visible

    def wait_for(self, state: str, timeout: float) -> None:
        if not self.visible:
            raise PlaywrightTimeoutError("not visible")


class FakeStatePage:
    def __init__(self, url: str, visible: set[str] | None = None) -> None:
        self.url = url
        self.visible = visible or set()

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector in self.visible)


def test_sign_in_url_is_logged_out() -> None:
    page = FakeStatePage("https://chat.deepseek.com/sign_in")

    assert get_provider("deepseek").detect_state(page) is PageState.LOGGED_OUT


def test_visible_password_field_is_logged_out() -> None:
    page = FakeStatePage("https://www.kimi.com/", {"input[type='password']"})

    assert get_provider("kimi").detect_state(page) is PageState.LOGGED_OUT


def test_visible_captcha_selector_is_captcha() -> None:
    page = FakeStatePage("https://wenxin.baidu.com/", {"[class*='captcha']"})

    assert get_provider("wenxin").detect_state(page) is PageState.CAPTCHA


def test_visible_composer_is_ready() -> None:
    page = FakeStatePage("https://chat.deepseek.com/", {"textarea"})

    assert get_provider("deepseek").detect_state(page) is PageState.READY


def test_empty_page_is_loading() -> None:
    page = FakeStatePage("https://chat.deepseek.com/")

    assert get_provider("deepseek").detect_state(page) is PageState.LOADING
