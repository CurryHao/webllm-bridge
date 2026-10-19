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

# Current kimi.com UI (K3, 2026): the composer is a Lexical editor
# ``div.chat-input-editor``; the send/stop control is a clickable
# ``div.send-button-container`` that gains the ``stop`` class while the answer
# streams. Assistant turns render inside ``div.segment.segment-assistant`` and
# the actions row (copy/share/...) lives in
# ``div.segment-assistant-actions`` as an icon-only button.
KIMI_INPUT_SELECTORS = (
    "div.chat-input-editor[contenteditable='true']",
) + COMMON_INPUT_SELECTORS

KIMI_BUSY_SELECTORS = (
    "div.send-button-container.stop",
    "div[class*='send-button-container'][class*='stop']",
    "svg[name='stop']",
) + COMMON_BUSY_SELECTORS

KIMI_ANSWER_SELECTORS = (
    "div.segment-assistant div.segment-content",
    "div.segment-assistant [class*='markdown-container']",
) + COMMON_ANSWER_SELECTORS

KIMI_NEW_SESSION_SELECTORS = (
    "a.new-chat-btn",
    "[aria-label='新建会话']",
    "button:has-text('新建会话')",
) + COMMON_NEW_SESSION_SELECTORS

KIMI_SEND_BUTTON_SELECTORS = (
    "div.send-button-container:not(.disabled)",
    "div.send-button-container",
) + COMMON_SEND_BUTTON_SELECTORS

KIMI_COPY_BUTTON_SELECTORS = (
    "div[class*='segment-assistant-actions'] svg[name='Copy']",
    "svg[name='Copy']",
) + COMMON_COPY_BUTTON_SELECTORS

KIMI_SOURCE_SELECTORS = (
    "[class*='search-tool-detail-item'][href]",
    "div.markdown a[href]",
) + COMMON_SOURCE_SELECTORS

KIMI_SPEC = ProviderSpec(
    name="kimi",
    display_name="Kimi",
    url="https://www.kimi.com/",
    hostnames=("www.kimi.com", "kimi.com", "kimi.moonshot.cn"),
    input_selectors=KIMI_INPUT_SELECTORS,
    busy_selectors=KIMI_BUSY_SELECTORS,
    answer_selectors=KIMI_ANSWER_SELECTORS,
    new_session_selectors=KIMI_NEW_SESSION_SELECTORS,
    send_button_selectors=KIMI_SEND_BUTTON_SELECTORS,
    copy_button_selectors=KIMI_COPY_BUTTON_SELECTORS,
    source_selectors=KIMI_SOURCE_SELECTORS,
    source_scope_selectors=("div.segment-assistant div.segment-content",),
    login_selectors=(
        "input[type='password']",
        "input[placeholder='手机号']",
        "input[placeholder='验证码']",
        "[class*='login-modal']",
        "[class*='login-desktop']",
        "button.login-button",
    ),
    captcha_selectors=(
        "iframe[src*='captcha']",
        "[class*='captcha']",
        "[class*='yidun_popup']",
    ),
    dynamic_selectors=(
        "div.segment-assistant",
        "[class*='segment-content']",
        "[class*='markdown-container']",
    ),
    ui_diff_threshold=0.04,
)


class KimiProvider(WebProvider):
    spec = KIMI_SPEC

    def _find_copy_button(self, page: Page, answer_bubble=None):
        # The copy control is a sibling of ``div.segment-content`` inside the
        # assistant segment, so search the actions row before the bubble.
        scopes = []
        try:
            actions = page.locator("div[class*='segment-assistant-actions']").last
            if actions.count():
                scopes.append(actions)
        except PlaywrightError:
            pass
        if answer_bubble is not None:
            scopes.append(answer_bubble)
        scopes.append(page)

        for scope in scopes:
            for selector in self.spec.copy_button_selectors:
                try:
                    candidate = scope.locator(selector).last
                    candidate.wait_for(state="visible", timeout=1500)
                except PlaywrightError:
                    continue
                return candidate
        return None
