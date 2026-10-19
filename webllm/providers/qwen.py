from __future__ import annotations

from webllm.providers.base import (
    COMMON_BUSY_SELECTORS,
    COMMON_COPY_BUTTON_SELECTORS,
    COMMON_INPUT_SELECTORS,
    COMMON_NEW_SESSION_SELECTORS,
    COMMON_SEND_BUTTON_SELECTORS,
    COMMON_SOURCE_SELECTORS,
    ProviderSpec,
    WebProvider,
)

QWEN_SPEC = ProviderSpec(
    name="qwen",
    display_name="千问",
    url="https://www.qianwen.com/",
    hostnames=("www.qianwen.com", "qianwen.com", "tongyi.aliyun.com"),
    input_selectors=COMMON_INPUT_SELECTORS,
    busy_selectors=COMMON_BUSY_SELECTORS,
    answer_selectors=(
        "[class*='markdown-body']",
        "[class*='qwen-markdown']",
        "[class*='answer-content']",
        "[class*='assistant-message']",
        "[data-role='assistant']",
    ),
    new_session_selectors=COMMON_NEW_SESSION_SELECTORS,
    send_button_selectors=COMMON_SEND_BUTTON_SELECTORS,
    copy_button_selectors=COMMON_COPY_BUTTON_SELECTORS,
    source_selectors=(
        "[class*='search-card'] a[href]",
        "[class*='reference'] a[href]",
        "[class*='citation'] a[href]",
    ) + COMMON_SOURCE_SELECTORS,
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
        "[class*='markdown-body']",
        "[class*='answer-content']",
    ),
)


class QwenProvider(WebProvider):
    spec = QWEN_SPEC
