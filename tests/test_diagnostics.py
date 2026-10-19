from __future__ import annotations

from pathlib import Path

from PIL import Image

from webllm import diagnostics
from webllm.diagnostics import HealthCheckConfig, PopupInfo, run_page_health
from webllm.states import PageState


def _solid(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (40, 30)) -> None:
    Image.new("RGB", size, color).save(path)


def test_compare_images_identical(tmp_path: Path) -> None:
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    _solid(first, (255, 255, 255))
    _solid(second, (255, 255, 255))

    ratio, changed, note = diagnostics.compare_images(first, second, threshold=0.03)

    assert ratio == 0.0
    assert changed is False
    assert note == ""


def test_compare_images_different(tmp_path: Path) -> None:
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    _solid(first, (255, 255, 255))
    _solid(second, (0, 0, 0))

    ratio, changed, _ = diagnostics.compare_images(first, second, threshold=0.03)

    assert ratio == 1.0
    assert changed is True


def test_compare_images_size_mismatch(tmp_path: Path) -> None:
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    _solid(first, (255, 255, 255), size=(40, 30))
    _solid(second, (255, 255, 255), size=(20, 10))

    ratio, changed, note = diagnostics.compare_images(first, second, threshold=0.03)

    assert ratio == 1.0
    assert changed is True
    assert "size mismatch" in note


class FakeEvaluatePage:
    def __init__(self, payload) -> None:
        self.payload = payload

    def evaluate(self, script: str, arg=None):
        return self.payload


def test_find_popups_maps_payload() -> None:
    page = FakeEvaluatePage(
        [
            {
                "selector": "[role='dialog']",
                "tag": "DIV",
                "class": "guide-modal",
                "text": "欢迎使用",
            }
        ]
    )

    popups = diagnostics.find_popups(page, ("[role='dialog']",))

    assert popups == [
        PopupInfo(selector="[role='dialog']", tag="DIV", class_name="guide-modal", text="欢迎使用")
    ]


class FakeDismissPage:
    def __init__(self) -> None:
        self.locator_calls: list[str] = []
        self.clicked = 0

    def locator(self, selector: str):
        self.locator_calls.append(selector)
        page = self

        class Wrapper:
            def count(self_inner) -> int:
                return 1

            def nth(self_inner, index: int):
                return self_inner

            def is_visible(self_inner) -> bool:
                return True

            def click(self_inner, timeout: float) -> None:
                page.clicked += 1

        return Wrapper()


def test_dismiss_popups_clicks_visible_buttons() -> None:
    page = FakeDismissPage()

    clicked = diagnostics.dismiss_popups(page, ("button:has-text('关闭')",))

    assert clicked == 1
    assert page.clicked == 1


class FakeProvider:
    class spec:
        name = "deepseek"
        display_name = "DeepSeek"
        popup_selectors = ("[role='dialog']",)
        popup_dismiss_selectors = ()
        dynamic_selectors = ()
        ui_diff_threshold = 0.03


def test_run_page_health_blocks_logged_out(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "find_popups", lambda page, selectors: [])

    report = run_page_health(
        FakeProvider(),
        page=object(),
        config=HealthCheckConfig(ui_check="off"),
        state=PageState.LOGGED_OUT,
    )

    assert report.blocking_code == "login_required"
    assert report.needs_human is True


def test_run_page_health_reports_remaining_popups(monkeypatch) -> None:
    popups = [PopupInfo(selector="[role='dialog']", text="引导弹窗")]
    monkeypatch.setattr(diagnostics, "find_popups", lambda page, selectors: popups)

    report = run_page_health(
        FakeProvider(),
        page=object(),
        config=HealthCheckConfig(ui_check="off", dismiss_popups=False, popup_error="error"),
        state=PageState.READY,
    )

    assert report.blocking_code == "popup_blocking"
    assert report.needs_human is True
