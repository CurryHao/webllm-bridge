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

ANTAFU_NEW_SESSION_SELECTORS = (
    "button:has-text('开启新对话')",
    "button[class*='newChatButton']",
) + COMMON_NEW_SESSION_SELECTORS

ANTAFU_SEND_BUTTON_SELECTORS = (
    "button[class*='sendButton']",
) + COMMON_SEND_BUTTON_SELECTORS

# Answers render as ``div.markdown-card.web-markdown-card`` wrapping the markdown
# body ``div.afu-markdown.mha-markdown-xui``; markdown answer cards can also be
# emitted as ``<div class="card-item" data-name="xui-card-markdown">``.
ANTAFU_ANSWER_SELECTORS = (
    "[class*='mha-markdown-xui']",
    "[class*='web-markdown-card']",
    "[class*='health-assistant-markdown-standard']",
    "div.card-item[data-name='xui-card-markdown']",
) + COMMON_ANSWER_SELECTORS

# Conversation modes offered on the new-chat screen. Accept both the CLI-style
# ASCII keys and the Chinese labels shown in the UI.
ANTAFU_MODES = {
    "deep_search": "深度搜索",
    "deepsearch": "深度搜索",
    "深度搜索": "深度搜索",
    "health_qa": "健康问答",
    "healthqa": "健康问答",
    "健康问答": "健康问答",
    "report": "报告解读",
    "report_reading": "报告解读",
    "报告解读": "报告解读",
    "medicine": "药盒识别",
    "drug": "药盒识别",
    "medicine_box": "药盒识别",
    "药盒识别": "药盒识别",
}

ANTAFU_SPEC = ProviderSpec(
    name="antafu",
    display_name="蚂蚁阿福",
    url="https://chat.antafu.com/",
    hostnames=("chat.antafu.com", "antafu.com"),
    input_selectors=COMMON_INPUT_SELECTORS,
    busy_selectors=COMMON_BUSY_SELECTORS,
    answer_selectors=ANTAFU_ANSWER_SELECTORS,
    new_session_selectors=ANTAFU_NEW_SESSION_SELECTORS,
    send_button_selectors=ANTAFU_SEND_BUTTON_SELECTORS,
    copy_button_selectors=COMMON_COPY_BUTTON_SELECTORS,
    source_selectors=(
        "[class*='rich-text-refer'] a[href]",
        "[class*='reference'] a[href]",
        "[class*='citation'] a[href]",
    ) + COMMON_SOURCE_SELECTORS,
    source_scope_selectors=("[class*='web-markdown-card']",),
    login_selectors=(
        "input[type='password']",
        "text=点击登录",
        "[class*='loginModal']",
        "[class*='loginButton']",
        "[class*='loginForm']",
        "[class*='loginPhone']",
    ),
    captcha_selectors=(
        "iframe[src*='captcha']",
        "[class*='captcha']",
    ),
    file_input_selectors=("input[type='file']",),
    dynamic_selectors=(
        "[class*='stream-message-renderer']",
        "[class*='mha-markdown-xui']",
    ),
)


class AntafuProvider(WebProvider):
    spec = ANTAFU_SPEC

    def select_mode(self, page: Page, mode: str) -> None:
        label = self._resolve_mode(mode)
        if label is None:
            supported = "、".join(dict.fromkeys(ANTAFU_MODES.values()))
            raise ValueError(f"Unknown Antafu mode: {mode}. Supported: {supported}.")

        locator = page.locator(f"div[class*='functionItem']:has-text('{label}')").last
        try:
            locator.wait_for(state="visible", timeout=5000)
        except PlaywrightError:
            raise RuntimeError(
                "Antafu modes can only be switched on a new session; "
                "start a new session before selecting a mode."
            ) from None

        if "activeFunction" in (locator.get_attribute("class") or ""):
            return
        locator.click()

    def attach_files(self, page: Page, paths: list[str]) -> None:
        super().attach_files(page, paths)
        try:
            page.locator("[class*='fileItem']").last.wait_for(state="visible", timeout=5000)
        except PlaywrightError:
            pass

    @staticmethod
    def _resolve_mode(mode: str | None) -> str | None:
        if mode is None:
            return None
        key = mode.strip()
        return ANTAFU_MODES.get(key) or ANTAFU_MODES.get(key.lower())
