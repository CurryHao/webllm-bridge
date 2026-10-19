from __future__ import annotations

import json

from webllm.models import Source
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

WENXIN_NEW_SESSION_SELECTORS = (
    "button:has-text('新建对话')",
    "button:has-text('新对话')",
    "div.new-dialog-container-button:has-text('开启新对话')",
    "div.new-dialog-container-button:has-text('新建对话')",
) + COMMON_NEW_SESSION_SELECTORS

WENXIN_COPY_BUTTON_SELECTORS = (
    "[data-testid='menu-btn-copy']",
) + COMMON_COPY_BUTTON_SELECTORS

WENXIN_SPEC = ProviderSpec(
    name="wenxin",
    display_name="文心一言",
    url="https://wenxin.baidu.com/",
    hostnames=("wenxin.baidu.com", "yiyan.baidu.com"),
    input_selectors=COMMON_INPUT_SELECTORS,
    busy_selectors=COMMON_BUSY_SELECTORS,
    answer_selectors=(
        "div.cosd-markdown",
        "[class*='cosd-markdown-content']",
        "[class*='cosd-markdown']",
        "[class*='markdown-body']",
        "[class*='answer-content']",
    ),
    new_session_selectors=WENXIN_NEW_SESSION_SELECTORS,
    send_button_selectors=COMMON_SEND_BUTTON_SELECTORS,
    copy_button_selectors=WENXIN_COPY_BUTTON_SELECTORS,
    source_selectors=(
        "[class*='reference'] a[href]",
        "[class*='search-result'] a[href]",
        "[class*='source'] a[href]",
    ) + COMMON_SOURCE_SELECTORS,
    source_scope_selectors=(
        "div.ai-entry",
        "[class*='answer-container']",
        "[class*='cs-answer-container']",
    ),
    source_item_selectors=("[class*='reference-item']",),
    login_url_patterns=(
        "/sign_in",
        "/login",
        "passport",
        "wappass",
        "/auth",
    ),
    login_selectors=(
        "input[type='password']",
        "[class*='login']",
        "iframe[src*='passport']",
        "text=登录",
    ),
    captcha_selectors=(
        "[class*='wappass']",
        "[class*='captcha']",
        "iframe[src*='captcha']",
    ),
    dynamic_selectors=(
        "div.ai-entry",
        "[class*='_reference']",
        "[class*='chat-search-answer']",
    ),
    ui_diff_threshold=0.04,
)


class WenxinProvider(WebProvider):
    spec = WENXIN_SPEC

    def _build_source(self, page, element, kind):
        raw = None
        try:
            raw = element.get_attribute("data-long-press-ext-info")
        except Exception:
            raw = None

        if raw:
            try:
                info = json.loads(raw)
            except (TypeError, ValueError):
                info = {}
            link = info.get("link") if isinstance(info, dict) else None
            if link:
                url = self._normalize_source_url(page, str(link))
                if url is not None:
                    title = str(info.get("linkTitle") or "").strip()
                    if not title:
                        title = self._element_text(element)
                    return Source(url=url, title=title[:300], snippet=title[:500], kind=kind)

        return super()._build_source(page, element, kind)
