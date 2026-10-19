from __future__ import annotations

from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright

from webllm.providers.base import ProviderSpec


class CdpConnectionError(RuntimeError):
    pass


class BrowserSession:
    """Connection to an existing Chromium instance over CDP.

    The agent owns the browser and its login state. This class never launches
    a browser and never closes user tabs on exit.
    """

    def __init__(self, cdp_url: str, timeout_ms: float = 30000) -> None:
        if "://" not in cdp_url:
            cdp_url = f"http://{cdp_url}"
        self.cdp_url = cdp_url
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._pages: dict[str, tuple[Page, bool]] = {}

    def __enter__(self) -> "BrowserSession":
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(
                self.cdp_url, timeout=self.timeout_ms
            )
        except PlaywrightError as exc:
            self._stop_playwright()
            raise CdpConnectionError(
                f"Could not connect to Chromium over CDP at {self.cdp_url}. "
                "Start the agent browser with --remote-debugging-port and log in first. "
                f"Original error: {exc}"
            ) from exc
        return self

    def __exit__(self, *args) -> None:
        self._pages.clear()
        if self._browser is not None:
            try:
                self._browser.close()
            except PlaywrightError:
                pass
            self._browser = None
        self._stop_playwright()

    def acquire_page(self, spec: ProviderSpec) -> Page:
        if self._browser is None:
            raise RuntimeError("BrowserSession is not connected.")

        existing = self._pages.get(spec.name)
        if existing is not None:
            page, _ = existing
            try:
                page.bring_to_front()
                return page
            except PlaywrightError:
                self._pages.pop(spec.name, None)

        candidates: list[tuple[int, Page]] = []
        for context in self._browser.contexts:
            for page in context.pages:
                try:
                    url = page.url
                except PlaywrightError:
                    continue
                score = self._host_score(url, spec)
                if score:
                    candidates.append((score, page))

        for _, page in sorted(candidates, key=lambda item: item[0], reverse=True):
            try:
                page.bring_to_front()
            except PlaywrightError:
                continue
            self._pages[spec.name] = (page, False)
            return page

        contexts = self._browser.contexts
        context = contexts[0] if contexts else self._browser.new_context()
        page = context.new_page()
        page.goto(spec.url, wait_until="domcontentloaded")
        page.bring_to_front()
        self._pages[spec.name] = (page, True)
        return page

    def page_url(self, provider_name: str) -> str:
        entry = self._pages.get(provider_name)
        if entry is None:
            return ""
        try:
            return entry[0].url
        except PlaywrightError:
            return ""

    def close_created_pages(self) -> None:
        for page, created in self._pages.values():
            if not created:
                continue
            try:
                page.close()
            except PlaywrightError:
                pass

    @classmethod
    def _matches_spec(cls, url: str, spec: ProviderSpec) -> bool:
        return cls._host_score(url, spec) > 0

    @staticmethod
    def _host_score(url: str, spec: ProviderSpec) -> int:
        try:
            hostname = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return 0
        if not hostname:
            return 0
        hostnames = tuple(candidate.lower() for candidate in spec.hostnames)
        if hostname in hostnames:
            return 2
        for candidate in hostnames:
            if hostname.endswith(f".{candidate}"):
                return 1
        return 0

    def _stop_playwright(self) -> None:
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except PlaywrightError:
                pass
            self._playwright = None
