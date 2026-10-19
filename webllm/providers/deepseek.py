from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from webllm.providers.base import (
    COMMON_ANSWER_SELECTORS,
    COMMON_BUSY_SELECTORS,
    COMMON_COPY_BUTTON_SELECTORS,
    COMMON_INPUT_SELECTORS,
    COMMON_NEW_SESSION_SELECTORS,
    COMMON_SEND_BUTTON_SELECTORS,
    COMMON_SOURCE_SELECTORS,
    ProviderSpec,
    WebProvider,
)

DEEPSEEK_COPY_BUTTON_SELECTORS = (
    "div[role='button'].ds-button--iconLabelTertiary:has(svg path[d^='M6.14929'])",
) + COMMON_COPY_BUTTON_SELECTORS

DEEPSEEK_DEEP_THINK_SELECTORS = (
    "div.ds-toggle-button:has-text('深度思考')",
    "div.ds-toggle-button:has-text('DeepThink')",
    "div.ds-toggle-button:has-text('Deep Think')",
)
DEEPSEEK_TOGGLE_SELECTED_CLASS = "ds-toggle-button--selected"

# The new-session entry differs by sidebar state on the current DeepSeek UI:
# expanded it is a ``div[tabindex=0]`` labeled "开启新对话"; collapsed it is an
# icon-only button whose "+" glyph uses this SVG path.
DEEPSEEK_NEW_SESSION_SELECTORS = (
    "div[role='button'].ds-button:has(svg path[d^='M8 0.599609'])",
    "div[tabindex='0']:has-text('开启新对话')",
) + COMMON_NEW_SESSION_SELECTORS

DEEPSEEK_SPEC = ProviderSpec(
    name="deepseek",
    display_name="DeepSeek",
    url="https://chat.deepseek.com/",
    hostnames=("chat.deepseek.com", "deepseek.com"),
    input_selectors=COMMON_INPUT_SELECTORS,
    busy_selectors=COMMON_BUSY_SELECTORS,
    answer_selectors=(
        "div.ds-assistant-message-main-content",
        "[class*='ds-assistant-message-main-content']",
        "[data-message-author-role='assistant']",
        "[data-role='assistant']",
        "[class*='assistant-message']",
        "[class*='answer-content']",
    ) + COMMON_ANSWER_SELECTORS,
    new_session_selectors=DEEPSEEK_NEW_SESSION_SELECTORS,
    send_button_selectors=COMMON_SEND_BUTTON_SELECTORS,
    copy_button_selectors=DEEPSEEK_COPY_BUTTON_SELECTORS,
    source_selectors=(
        "[class*='citation'] a[href]",
        "[class*='reference'] a[href]",
        "[class*='search-result'] a[href]",
    ) + COMMON_SOURCE_SELECTORS,
    source_scope_selectors=("div.ds-message", "div.ds-assistant-message-main-content"),
    login_selectors=(
        "input[type='password']",
        "text=登录",
        "[class*='login']",
    ),
    captcha_selectors=(
        "iframe[src*='captcha']",
        "[class*='captcha']",
    ),
    dynamic_selectors=(
        "div.ds-message",
        "[class*='ds-virtual-list']",
        "[class*='ds-scroll-area']",
    ),
    ui_diff_threshold=0.04,
)


class DeepSeekProvider(WebProvider):
    spec = DEEPSEEK_SPEC

    def prepare_for_question(self, page: Page) -> None:
        self.ensure_deep_think(page)

    def ensure_deep_think(self, page: Page, timeout: float = 2000) -> bool:
        """Enable the DeepThink toggle when it is off.

        Returns ``True`` when the toggle was found and clicked, ``False`` when
        it was already enabled or could not be located. Best effort: a missing
        toggle never blocks the question.
        """
        for selector in DEEPSEEK_DEEP_THINK_SELECTORS:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout)
            except PlaywrightError:
                continue
            if self._deep_think_enabled(locator):
                return False
            try:
                locator.click(timeout=timeout)
            except PlaywrightError:
                continue
            return True
        return False

    @staticmethod
    def _deep_think_enabled(locator) -> bool:
        try:
            if (locator.get_attribute("aria-pressed") or "").lower() == "true":
                return True
            classes = locator.get_attribute("class") or ""
        except PlaywrightError:
            return False
        return DEEPSEEK_TOGGLE_SELECTED_CLASS in classes
