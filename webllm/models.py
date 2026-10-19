from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NEEDS_HUMAN_CODES = frozenset(
    {"login_required", "captcha_required", "rate_limited", "popup_blocking"}
)


@dataclass(frozen=True)
class Source:
    url: str
    title: str = ""
    snippet: str = ""
    kind: str = "link"

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "kind": self.kind,
        }


@dataclass
class Answer:
    provider: str
    question: str
    answer: str = ""
    sources: list[Source] = field(default_factory=list)
    session_url: str = ""
    elapsed_seconds: float = 0.0
    captured_by: str = "none"
    new_session: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "error",
            "provider": self.provider,
            "question": self.question,
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
            "session_url": self.session_url,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "captured_by": self.captured_by,
            "new_session": self.new_session,
            "warnings": list(self.warnings),
            "error": self.error,
            "error_code": self.error_code,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass
class BatchResult:
    provider: str
    display_name: str
    results: list[Answer] = field(default_factory=list)
    session_url: str = ""
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    @property
    def needs_human(self) -> bool:
        return any(result.error_code in NEEDS_HUMAN_CODES for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "needs_human": self.needs_human,
            "provider": self.provider,
            "provider_name": self.display_name,
            "session_url": self.session_url,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "results": [result.to_dict() for result in self.results],
        }
