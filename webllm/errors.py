from __future__ import annotations

from typing import Any

from webllm.states import PageState


class WebLLMError(RuntimeError):
    """Typed error carrying an agent-readable code and diagnostics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        state: PageState | None = None,
        retryable: bool = False,
        screenshot: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.state = state
        self.retryable = retryable
        self.screenshot = screenshot
        self.diagnostics = diagnostics or {}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.state is not None:
            payload["state"] = self.state.value
        if self.screenshot:
            payload["screenshot"] = self.screenshot
        if self.diagnostics:
            payload["diagnostics"] = self.diagnostics
        return payload
