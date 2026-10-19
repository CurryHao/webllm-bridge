from __future__ import annotations

from enum import Enum


class PageState(str, Enum):
    READY = "ready"
    LOADING = "loading"
    LOGGED_OUT = "logged_out"
    CAPTCHA = "captcha"
    RATE_LIMITED = "rate_limited"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


NEEDS_HUMAN_STATES = frozenset(
    {PageState.LOGGED_OUT, PageState.CAPTCHA, PageState.RATE_LIMITED}
)

STATE_ERROR_CODES = {
    PageState.LOGGED_OUT: "login_required",
    PageState.CAPTCHA: "captcha_required",
    PageState.RATE_LIMITED: "rate_limited",
    PageState.MAINTENANCE: "maintenance",
}
