from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from webllm.providers import get_provider, list_providers
from webllm.providers.base import AnswerFingerprint, Capture
from webllm.providers.deepseek import DeepSeekProvider
from webllm.providers.wenxin import WenxinProvider


class FakeInput:
    def __init__(self, question: str, *, clear_on_enter: bool = True, typing_lands: bool = True) -> None:
        self.question = question
        self.clear_on_enter = clear_on_enter
        self.typing_lands = typing_lands
        self.text = ""
        self.events: list[str] = []

    def click(self) -> None:
        self.events.append("click")

    def press(self, key: str) -> None:
        self.events.append(f"press:{key}")
        if key == "Enter" and self.clear_on_enter:
            self.text = ""

    def type(self, text: str, delay: float | None = None) -> None:
        self.events.append(f"type:{text}")
        if self.typing_lands:
            self.text = text

    def fill(self, text: str) -> None:
        self.events.append(f"fill:{text}")
        self.text = text

    def input_value(self, timeout: float | None = None) -> str:
        return self.text

    def inner_text(self, timeout: float | None = None) -> str:
        return self.text


class FakeVisibleInput:
    def __init__(self) -> None:
        self.waited = False

    def wait_for(self, state: str, timeout: float) -> None:
        self.waited = True


class FlakyInputPage:
    def __init__(self, fail_first_calls: int) -> None:
        self.fail_first_calls = fail_first_calls
        self.calls = 0
        self.input = FakeVisibleInput()

    def locator(self, selector: str):
        self.calls += 1
        if self.calls <= self.fail_first_calls:
            return MissingLocator()
        return FakeList([self.input])


class FakeWaitPage:
    def wait_for_timeout(self, milliseconds: float) -> None:
        time.sleep(milliseconds / 1000)


def test_wait_for_answer_start_uses_seconds(monkeypatch) -> None:
    provider = DeepSeekProvider()
    sequence = [
        AnswerFingerprint(node_count=1, last_text="a"),
        AnswerFingerprint(node_count=1, last_text="a"),
        AnswerFingerprint(node_count=2, last_text="b"),
    ]
    calls = {"index": 0}

    def fingerprint(page):
        index = min(calls["index"], len(sequence) - 1)
        calls["index"] += 1
        return sequence[index]

    monkeypatch.setattr(provider, "answer_fingerprint", fingerprint)

    changed = provider.wait_for_answer_start(
        FakeWaitPage(), AnswerFingerprint(node_count=1, last_text="a"), timeout=1
    )

    assert changed is True


def test_find_input_retries_while_login_restores(monkeypatch) -> None:
    from webllm.providers import base as base_module

    clock = {"now": 0.0}
    monkeypatch.setattr(base_module.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        base_module.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    page = FlakyInputPage(fail_first_calls=3)

    locator = DeepSeekProvider().find_input(page, timeout=30000)

    assert locator.waited is True
    assert page.calls > 3


def test_submit_types_and_presses_enter(monkeypatch) -> None:
    provider = DeepSeekProvider()
    fake_input = FakeInput("问题")
    monkeypatch.setattr(provider, "find_input", lambda page: fake_input)

    provider.submit(None, "问题")

    assert fake_input.events == [
        "click",
        "press:Control+a",
        "press:Delete",
        "type:问题",
        "press:Enter",
    ]


def test_submit_falls_back_to_fill(monkeypatch) -> None:
    provider = DeepSeekProvider()
    fake_input = FakeInput("问题", typing_lands=False)
    monkeypatch.setattr(provider, "find_input", lambda page: fake_input)

    provider.submit(None, "问题")

    assert "fill:问题" in fake_input.events


def test_submit_clicks_send_when_enter_keeps_text(monkeypatch) -> None:
    provider = DeepSeekProvider()
    fake_input = FakeInput("问题", clear_on_enter=False)
    monkeypatch.setattr(provider, "find_input", lambda page: fake_input)
    monkeypatch.setattr(provider, "_input_still_contains", lambda *args, **kwargs: True)
    monkeypatch.setattr(provider, "_click_send_button", lambda page: fake_input.events.append("send"))

    provider.submit(None, "问题")

    assert fake_input.events[-1] == "send"


class MissingLocator:
    @property
    def first(self) -> "MissingLocator":
        return self

    def wait_for(self, state: str, timeout: float) -> None:
        raise PlaywrightTimeoutError("not found")

    def click(self, timeout: float) -> None:
        raise PlaywrightTimeoutError("not found")


class FakeList:
    def __init__(self, items: list[object] | None = None) -> None:
        self.items = list(items or [])

    def count(self) -> int:
        return len(self.items)

    def nth(self, index: int):
        return self.items[index]

    @property
    def first(self):
        return self.items[0] if self.items else MissingLocator()

    @property
    def last(self):
        return self.items[-1] if self.items else MissingLocator()

    def locator(self, selector: str) -> "FakeList":
        return FakeList()

    def get_attribute(self, name: str) -> str | None:
        return None

    def inner_text(self, timeout: float | None = None) -> str:
        return ""


class FakeAnchor:
    def __init__(self, href: str, text: str) -> None:
        self.href = href
        self.text = text

    def get_attribute(self, name: str) -> str | None:
        return self.href if name == "href" else None

    def inner_text(self, timeout: float | None = None) -> str:
        return self.text

    def locator(self, selector: str) -> FakeList:
        return FakeList()


class FakeBubble(FakeAnchor):
    def __init__(self, anchors: list[FakeAnchor]) -> None:
        super().__init__("", "")
        self.anchors = anchors
        self.hovered = False

    def hover(self, timeout: float | None = None) -> None:
        self.hovered = True

    def locator(self, selector: str) -> FakeList:
        if selector == "a[href]":
            return FakeList(self.anchors)
        return FakeList()


class FakeSourcePage:
    def __init__(self, bubble: FakeBubble, answer_selector: str) -> None:
        self.bubble = bubble
        self.answer_selector = answer_selector
        self.url = "https://chat.deepseek.com/a/chat/123"

    def locator(self, selector: str) -> FakeList:
        if selector == self.answer_selector:
            return FakeList([self.bubble])
        return FakeList()


def test_extract_sources_returns_external_links_and_deduplicates() -> None:
    provider = DeepSeekProvider()
    bubble = FakeBubble(
        [
            FakeAnchor("https://example.com/a", "Example A"),
            FakeAnchor("https://example.com/a", "Duplicate"),
            FakeAnchor("/relative", "Relative"),
            FakeAnchor("https://chat.deepseek.com/chat", "Internal"),
            FakeAnchor("https://www.deepseek.com/chat", "Internal subdomain"),
            FakeAnchor("javascript:void(0)", "Bad"),
        ]
    )
    page = FakeSourcePage(bubble, provider.spec.answer_selectors[0])

    sources = provider.extract_sources(page)

    assert [source.url for source in sources] == ["https://example.com/a"]
    assert sources[0].title == "Example A"
    assert bubble.hovered is False


def test_kimi_targets_current_web_ui() -> None:
    spec = get_provider("kimi").spec

    assert spec.input_selectors[0] == "div.chat-input-editor[contenteditable='true']"
    assert spec.answer_selectors[0] == "div.segment-assistant div.segment-content"
    assert any("send-button-container" in selector for selector in spec.send_button_selectors)
    assert any("stop" in selector for selector in spec.busy_selectors)
    assert any("new-chat-btn" in selector for selector in spec.new_session_selectors)
    assert any("Copy" in selector for selector in spec.copy_button_selectors)


class FakeCopyIcon:
    def wait_for(self, state: str, timeout: float) -> None:
        return None


class FakeActionRow:
    def __init__(self, icons: list[FakeCopyIcon]) -> None:
        self.icons = icons

    def count(self) -> int:
        return 1

    def locator(self, selector: str) -> FakeList:
        if "svg" in selector:
            return FakeList(self.icons)
        return FakeList()


class FakeKimiPage:
    def __init__(self, row: FakeActionRow | None) -> None:
        self.row = row

    def locator(self, selector: str) -> FakeList:
        if self.row is not None and "segment-assistant-actions" in selector:
            return FakeList([self.row])
        return FakeList()


def test_kimi_prefers_assistant_action_copy_button() -> None:
    icon = FakeCopyIcon()
    provider = get_provider("kimi")

    button = provider._find_copy_button(FakeKimiPage(FakeActionRow([icon])))

    assert button is icon


def test_provider_registry_exposes_all_provider_specs() -> None:
    names = {provider["name"] for provider in list_providers()}

    assert names == {"deepseek", "qwen", "kimi", "wenxin", "antafu"}
    assert get_provider("deepseek").spec.url == "https://chat.deepseek.com/"
    assert get_provider("qwen").spec.url == "https://www.qianwen.com/"
    assert get_provider("kimi").spec.url == "https://www.kimi.com/"
    assert get_provider("antafu").spec.url == "https://chat.antafu.com/"


def test_antafu_targets_answer_card_and_new_chat() -> None:
    spec = get_provider("antafu").spec

    assert spec.answer_selectors[0] == "[class*='mha-markdown-xui']"
    assert any("sendButton" in selector for selector in spec.send_button_selectors)
    assert any("开启新对话" in selector for selector in spec.new_session_selectors)


def test_antafu_resolves_mode_aliases() -> None:
    provider = get_provider("antafu")

    assert provider._resolve_mode("deep_search") == "深度搜索"
    assert provider._resolve_mode("REPORT") == "报告解读"
    assert provider._resolve_mode("药盒识别") == "药盒识别"
    assert provider._resolve_mode("nope") is None
    assert provider._resolve_mode(None) is None


class FakeModeItem:
    def __init__(self, active: bool) -> None:
        self.active = active
        self.clicked = False

    def wait_for(self, state: str, timeout: float) -> None:
        return None

    def get_attribute(self, name: str) -> str | None:
        if name == "class":
            if self.active:
                return "functionItem-6Ogg589Q activeFunction-DxWCz0wq"
            return "functionItem-6Ogg589Q"
        return None

    def click(self, timeout: float | None = None) -> None:
        self.clicked = True


class FakeModePage:
    def __init__(self, item: FakeModeItem) -> None:
        self.item = item

    def locator(self, selector: str) -> FakeList:
        return FakeList([self.item])


def test_antafu_select_mode_clicks_inactive_item() -> None:
    item = FakeModeItem(active=False)

    get_provider("antafu").select_mode(FakeModePage(item), "health_qa")

    assert item.clicked is True


def test_antafu_select_mode_skips_active_item() -> None:
    item = FakeModeItem(active=True)

    get_provider("antafu").select_mode(FakeModePage(item), "报告解读")

    assert item.clicked is False


def test_antafu_select_mode_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="Unknown Antafu mode"):
        get_provider("antafu").select_mode(FakeModePage(FakeModeItem(False)), "bogus")


class FakeFileInput:
    def __init__(self) -> None:
        self.files: list[str] | None = None
        self.found = True

    @property
    def first(self) -> "FakeFileInput":
        return self

    def count(self) -> int:
        return 1 if self.found else 0

    def set_input_files(self, files, timeout: float | None = None) -> None:
        self.files = list(files)


class FakePreview(FakeList):
    @property
    def last(self) -> "FakePreview":
        return self

    def wait_for(self, state: str, timeout: float) -> None:
        return None


class FakeUploadPage:
    def __init__(self, file_input: FakeFileInput) -> None:
        self.file_input = file_input

    def locator(self, selector: str) -> object:
        if "fileItem" in selector:
            return FakePreview()
        return self.file_input


def test_antafu_has_file_input_selector() -> None:
    assert get_provider("antafu").spec.file_input_selectors == ("input[type='file']",)


def test_antafu_attach_files_uploads(tmp_path) -> None:
    report = tmp_path / "report.png"
    report.write_bytes(b"png")
    file_input = FakeFileInput()

    get_provider("antafu").attach_files(FakeUploadPage(file_input), [str(report)])

    assert file_input.files == [str(report)]


def test_attach_files_missing_file_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="Attachment not found"):
        get_provider("antafu").attach_files(
            FakeUploadPage(FakeFileInput()), [str(tmp_path / "nope.png")]
        )


def test_attach_files_unsupported_provider_raises() -> None:
    with pytest.raises(RuntimeError, match="does not support file upload"):
        get_provider("deepseek").attach_files(FakeUploadPage(FakeFileInput()), ["x.png"])


def test_deepseek_targets_full_answer_and_message_copy_button() -> None:
    spec = DeepSeekProvider.spec

    assert spec.answer_selectors[0] == "div.ds-assistant-message-main-content"
    assert "div.ds-message" in spec.source_scope_selectors
    assert any("ds-button--iconLabelTertiary" in selector for selector in spec.copy_button_selectors)


def test_deepseek_new_session_covers_expanded_and_collapsed_sidebar() -> None:
    selectors = DeepSeekProvider.spec.new_session_selectors

    assert any("开启新对话" in selector for selector in selectors)
    assert any("M8 0.599609" in selector for selector in selectors)


class FakeToggle:
    def __init__(self, selected: bool) -> None:
        self.selected = selected
        self.clicked = False
        self.waited = False

    def wait_for(self, state: str, timeout: float) -> None:
        self.waited = True

    def get_attribute(self, name: str) -> str | None:
        if name == "aria-pressed":
            return "true" if self.selected else "false"
        if name == "class":
            classes = "ds-toggle-button ds-toggle-button--m"
            return f"{classes} ds-toggle-button--selected" if self.selected else classes
        return None

    def click(self, timeout: float | None = None) -> None:
        self.clicked = True
        self.selected = True


class FakeTogglePage:
    def __init__(self, toggle: FakeToggle) -> None:
        self.toggle = toggle

    def locator(self, selector: str) -> FakeList:
        if "ds-toggle-button" in selector:
            return FakeList([self.toggle])
        return FakeList()


def test_deepseek_enables_deep_think_when_disabled() -> None:
    toggle = FakeToggle(selected=False)

    changed = DeepSeekProvider().ensure_deep_think(FakeTogglePage(toggle))

    assert changed is True
    assert toggle.clicked is True
    assert toggle.selected is True


def test_deepseek_keeps_deep_think_when_already_enabled() -> None:
    toggle = FakeToggle(selected=True)

    changed = DeepSeekProvider().ensure_deep_think(FakeTogglePage(toggle))

    assert changed is False
    assert toggle.clicked is False


def test_deepseek_prepare_enables_deep_think(monkeypatch) -> None:
    provider = DeepSeekProvider()
    calls: list[object] = []
    monkeypatch.setattr(provider, "ensure_deep_think", lambda page: calls.append(page))

    provider.prepare_for_question("page")

    assert calls == ["page"]


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("nope")


def test_wenxin_has_provider_specific_new_session_selector() -> None:
    assert "button:has-text('新建对话')" in WenxinProvider.spec.new_session_selectors


class FakeCopyButton:
    def __init__(self) -> None:
        self.clicked = False

    def wait_for(self, state: str, timeout: float) -> None:
        return None

    def click(self, timeout: float) -> None:
        self.clicked = True


class FakeCdpSession:
    def __init__(self, text: str) -> None:
        self.text = text
        self.detached = False

    def send(self, method: str) -> dict[str, str]:
        assert method == "Clipboard.readText"
        return {"text": self.text}

    def detach(self) -> None:
        self.detached = True


class FakeContext:
    def __init__(self, clipboard_text: str) -> None:
        self.clipboard_text = clipboard_text
        self.granted: list[list[str]] = []

    def grant_permissions(self, permissions: list[str], **kwargs) -> None:
        self.granted.append(permissions)

    def new_cdp_session(self, page):
        return FakeCdpSession(self.clipboard_text)


class FakeCapturePage:
    def __init__(self, bubble: FakeBubble, button: FakeCopyButton | None, clipboard_text: str) -> None:
        self.bubble = bubble
        self.button = button
        self.url = "https://chat.deepseek.com/a/chat/1"
        self.context = FakeContext(clipboard_text)
        self.evaluated: list[tuple[str, str]] = []

    def locator(self, selector: str) -> FakeList:
        if selector == DeepSeekProvider.spec.answer_selectors[0]:
            return FakeList([self.bubble])
        return FakeList()

    def evaluate(self, script: str, arg: str | None = None):
        if arg is not None:
            self.evaluated.append((script, arg))
        return ""

    def wait_for_timeout(self, timeout: float) -> None:
        return None


class CopyBubble(FakeBubble):
    def __init__(self, button: FakeCopyButton | None, text: str = "inner text") -> None:
        super().__init__([])
        self.button = button
        self.text = text

    def inner_text(self, timeout: float | None = None) -> str:
        return self.text

    def locator(self, selector: str) -> FakeList:
        if self.button is not None and selector == "button:has-text('复制')":
            return FakeList([self.button])
        return FakeList()


def test_capture_answer_uses_copy_button_and_clipboard() -> None:
    button = FakeCopyButton()
    bubble = CopyBubble(button)
    page = FakeCapturePage(bubble, button, "复制的答案")

    capture = DeepSeekProvider().capture_answer(page)

    assert capture == Capture("复制的答案", "copy")
    assert button.clicked is True
    assert bubble.hovered is True
    assert page.evaluated


def test_capture_answer_falls_back_to_bubble_text() -> None:
    bubble = CopyBubble(None, "页面里的答案")
    page = FakeCapturePage(bubble, None, "")

    capture = DeepSeekProvider().capture_answer(page)

    assert capture == Capture("页面里的答案", "text")


class FakeReference:
    def __init__(self, payload: str, text: str = "") -> None:
        self.payload = payload
        self.text = text

    def get_attribute(self, name: str) -> str | None:
        if name == "data-long-press-ext-info":
            return self.payload
        return None

    def inner_text(self, timeout: float | None = None) -> str:
        return self.text

    def locator(self, selector: str) -> FakeList:
        return FakeList()


class FakeWenxinScope(FakeBubble):
    def __init__(self, items: list[FakeReference]) -> None:
        super().__init__([])
        self.items = items

    def locator(self, selector: str) -> FakeList:
        if selector == "[class*='reference-item']":
            return FakeList(self.items)
        return super().locator(selector)


class FakeWenxinPage:
    def __init__(self, scope: FakeWenxinScope) -> None:
        self.scope = scope
        self.url = "https://wenxin.baidu.com/search/1"

    def locator(self, selector: str) -> FakeList:
        if selector in WenxinProvider.spec.source_scope_selectors:
            return FakeList([self.scope])
        return FakeList()


def test_wenxin_uses_cosd_markdown_answer_selector() -> None:
    assert "div.cosd-markdown" in WenxinProvider.spec.answer_selectors


def test_wenxin_extracts_reference_items_from_data_attribute() -> None:
    payload = json.dumps(
        {"link": "https://docs.opencode.ai/docs/", "linkTitle": "Intro"},
        ensure_ascii=False,
    )
    scope = FakeWenxinScope([FakeReference(payload, "1. Intro-docs.opencode.ai")])
    page = FakeWenxinPage(scope)

    sources = WenxinProvider().extract_sources(page)

    assert [source.url for source in sources] == ["https://docs.opencode.ai/docs/"]
    assert sources[0].title == "Intro"
