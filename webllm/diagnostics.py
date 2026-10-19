from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from webllm.states import NEEDS_HUMAN_STATES, PageState

VIEWPORTS: dict[str, dict[str, int]] = {
    "small": {"width": 1280, "height": 800},
    "large": {"width": 1920, "height": 1080},
}

DEFAULT_BASELINE_DIR = Path(".webllm/baselines")
DEFAULT_SCREENSHOT_DIR = Path(".webllm/screenshots")
DIFF_PIXEL_THRESHOLD = 16
DIFF_RATIO_THRESHOLD = 0.03


@dataclass
class PopupInfo:
    selector: str
    tag: str = ""
    class_name: str = ""
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "tag": self.tag,
            "class_name": self.class_name,
            "text": self.text,
        }


@dataclass
class UiDiffResult:
    viewport: str
    diff_ratio: float
    threshold: float
    changed: bool
    baseline_action: str
    screenshot: str = ""
    diff_image: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewport": self.viewport,
            "diff_ratio": round(self.diff_ratio, 4),
            "threshold": self.threshold,
            "changed": self.changed,
            "baseline_action": self.baseline_action,
            "screenshot": self.screenshot,
            "diff_image": self.diff_image,
            "note": self.note,
        }


@dataclass
class PageHealthReport:
    provider: str
    state: PageState
    popups: list[PopupInfo] = field(default_factory=list)
    dismissed_popups: int = 0
    ui_diffs: list[UiDiffResult] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_code: str | None = None

    @property
    def needs_human(self) -> bool:
        return self.blocking_code in {
            "login_required",
            "captcha_required",
            "rate_limited",
            "popup_blocking",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "state": self.state.value,
            "needs_human": self.needs_human,
            "blocking_code": self.blocking_code,
            "popups": [popup.to_dict() for popup in self.popups],
            "dismissed_popups": self.dismissed_popups,
            "ui_diffs": [diff.to_dict() for diff in self.ui_diffs],
            "warnings": list(self.warnings),
            "screenshots": list(self.screenshots),
        }


@dataclass
class HealthCheckConfig:
    baselines_dir: Path = DEFAULT_BASELINE_DIR
    screenshots_dir: Path = DEFAULT_SCREENSHOT_DIR
    viewports: tuple[str, ...] = ("small", "large")
    ui_check: str = "warn"
    diff_threshold: float | None = None
    update_baseline: bool = False
    dismiss_popups: bool = True
    popup_error: str = "warn"

    def threshold_for(self, provider_threshold: float) -> float:
        if self.diff_threshold is not None:
            return self.diff_threshold
        return provider_threshold


def resolve_viewports(value: str) -> tuple[str, ...]:
    if value == "both":
        return ("small", "large")
    if value in VIEWPORTS:
        return (value,)
    raise ValueError(f"Unknown viewport option: {value}. Use small, large, or both.")


def find_popups(page: Page, selectors: tuple[str, ...]) -> list[PopupInfo]:
    if not selectors:
        return []
    try:
        raw = page.evaluate(_POPUP_SCRIPT, list(selectors))
    except PlaywrightError:
        return []
    return [
        PopupInfo(
            selector=str(item.get("selector", "")),
            tag=str(item.get("tag", "")),
            class_name=str(item.get("class", "")),
            text=str(item.get("text", "")),
        )
        for item in (raw or [])
    ]


def dismiss_popups(page: Page, selectors: tuple[str, ...]) -> int:
    if not selectors:
        return 0
    clicked = 0
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except PlaywrightError:
            continue
        for index in range(min(count, 5)):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible():
                    continue
                candidate.click(timeout=1000)
                clicked += 1
            except Exception:
                continue
    return clicked


def run_page_health(
    provider,
    page: Page,
    config: HealthCheckConfig,
    state: PageState,
) -> PageHealthReport:
    report = PageHealthReport(provider=provider.spec.name, state=state)

    popup_selectors = provider.spec.popup_selectors
    report.popups = find_popups(page, popup_selectors)
    if report.popups and config.dismiss_popups:
        report.dismissed_popups = dismiss_popups(page, provider.spec.popup_dismiss_selectors)
        if report.dismissed_popups:
            page.wait_for_timeout(300)
            report.popups = find_popups(page, popup_selectors)

    if config.ui_check != "off" or config.update_baseline:
        report.ui_diffs, report.screenshots = _check_ui(provider, page, config)

    for diff in report.ui_diffs:
        if diff.changed:
            report.warnings.append(
                f"{provider.spec.display_name} UI changed at {diff.viewport} viewport "
                f"(diff {diff.diff_ratio:.3f} > {diff.threshold:.3f})."
            )
        if diff.baseline_action == "created":
            report.warnings.append(
                f"Created {diff.viewport} baseline for {provider.spec.display_name}."
            )

    if state in NEEDS_HUMAN_STATES:
        from webllm.states import STATE_ERROR_CODES

        report.blocking_code = STATE_ERROR_CODES.get(state, "page_not_ready")
    elif config.ui_check == "error" and any(diff.changed for diff in report.ui_diffs):
        report.blocking_code = "ui_changed"
    elif report.popups and config.popup_error == "error":
        report.blocking_code = "popup_blocking"

    return report


def check_ready(
    provider,
    page: Page,
    *,
    timeout: float,
    wait_human: float,
    screenshot_dir: Path,
) -> tuple[PageState, str | None]:
    """Wait for a usable page state. Returns (state, evidence screenshot path)."""
    deadline = time.monotonic() + (wait_human if wait_human > 0 else timeout)
    last_state = PageState.UNKNOWN
    while True:
        last_state = provider.detect_state(page)
        if last_state is PageState.READY:
            return last_state, None
        if wait_human <= 0:
            break
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(1000)

    screenshot = capture_evidence(page, screenshot_dir, provider.spec.name, last_state.value)
    return last_state, screenshot


def capture_evidence(
    page: Page, directory: Path, provider: str, label: str
) -> str | None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{provider}-{label}-{int(time.time())}.png"
        page.screenshot(path=str(path), animations="disabled")
        return str(path)
    except Exception:
        return None


def compare_images(
    baseline_path: Path,
    current_path: Path,
    threshold: float,
    diff_path: Path | None = None,
) -> tuple[float, bool, str]:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return _compare_bytes(baseline_path, current_path)

    with Image.open(baseline_path) as baseline_image:
        baseline = baseline_image.convert("RGB")
    with Image.open(current_path) as current_image:
        current = current_image.convert("RGB")

    if baseline.size != current.size:
        if diff_path is not None:
            _save_resize_hint(current, diff_path)
        return 1.0, True, f"size mismatch {baseline.size} != {current.size}"

    diff = ImageChops.difference(baseline, current).convert("L")
    histogram = diff.histogram()
    total = sum(histogram)
    changed_pixels = sum(histogram[DIFF_PIXEL_THRESHOLD:])
    ratio = changed_pixels / total if total else 0.0

    if diff_path is not None:
        try:
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff.save(diff_path)
        except Exception:
            pass

    return ratio, ratio > threshold, ""


def _compare_bytes(baseline_path: Path, current_path: Path) -> tuple[float, bool, str]:
    baseline = baseline_path.read_bytes()
    current = current_path.read_bytes()
    changed = baseline != current
    return (1.0 if changed else 0.0), changed, "pillow-unavailable"


def _save_resize_hint(image, diff_path: Path) -> None:
    try:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(diff_path)
    except Exception:
        pass


def _check_ui(
    provider, page: Page, config: HealthCheckConfig
) -> tuple[list[UiDiffResult], list[str]]:
    results: list[UiDiffResult] = []
    screenshots: list[str] = []
    original_viewport = page.viewport_size
    measured = None
    if original_viewport is None:
        try:
            measured = page.evaluate(
                "() => ({ width: window.innerWidth, height: window.innerHeight })"
            )
        except PlaywrightError:
            measured = None

    try:
        for name in config.viewports:
            viewport = VIEWPORTS.get(name)
            if viewport is None:
                continue
            try:
                page.set_viewport_size(viewport)
            except Exception:
                continue
            page.wait_for_timeout(400)

            config.baselines_dir.mkdir(parents=True, exist_ok=True)
            config.screenshots_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time() * 1000)
            current_path = config.screenshots_dir / f"{provider.spec.name}-{name}-{stamp}.png"
            _capture(page, current_path, provider.spec.dynamic_selectors)
            screenshots.append(str(current_path))

            baseline_path = config.baselines_dir / f"{provider.spec.name}-{name}.png"
            threshold = config.threshold_for(provider.spec.ui_diff_threshold)
            if config.update_baseline or not baseline_path.exists():
                action = "updated" if baseline_path.exists() else "created"
                baseline_path.write_bytes(current_path.read_bytes())
                results.append(
                    UiDiffResult(
                        viewport=name,
                        diff_ratio=0.0,
                        threshold=threshold,
                        changed=False,
                        baseline_action=action,
                        screenshot=str(current_path),
                    )
                )
                continue

            diff_path = config.screenshots_dir / f"{provider.spec.name}-{name}-{stamp}-diff.png"
            ratio, changed, note = compare_images(
                baseline_path, current_path, threshold, diff_path
            )
            results.append(
                UiDiffResult(
                    viewport=name,
                    diff_ratio=ratio,
                    threshold=threshold,
                    changed=changed,
                    baseline_action="compared",
                    screenshot=str(current_path),
                    diff_image=str(diff_path) if changed else "",
                    note=note,
                )
            )
    finally:
        restore = original_viewport if original_viewport is not None else measured
        if restore is not None:
            try:
                page.set_viewport_size(restore)
            except Exception:
                pass

    return results, screenshots


def _capture(page: Page, path: Path, mask_selectors: tuple[str, ...]) -> None:
    masks = []
    for selector in mask_selectors:
        try:
            masks.append(page.locator(selector))
        except PlaywrightError:
            continue
    try:
        page.screenshot(
            path=str(path),
            animations="disabled",
            mask=masks or None,
        )
    except PlaywrightError:
        page.screenshot(path=str(path), animations="disabled")


_POPUP_SCRIPT = """
(selectors) => {
    const results = [];
    const seen = new Set();
    for (const selector of selectors) {
        let nodes;
        try {
            nodes = document.querySelectorAll(selector);
        } catch (error) {
            continue;
        }
        for (const el of nodes) {
            if (seen.has(el)) continue;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const visible =
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                parseFloat(style.opacity || "1") > 0 &&
                rect.width > 20 &&
                rect.height > 20;
            if (!visible) continue;
            seen.add(el);
            results.push({
                tag: el.tagName,
                class: (el.className || "").toString().slice(0, 150),
                text: (el.innerText || "").trim().slice(0, 200),
                selector: selector,
            });
            if (results.length >= 20) return results;
        }
    }
    return results;
}
"""
