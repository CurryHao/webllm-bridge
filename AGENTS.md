# AGENTS.md

## Overview
Agent-oriented Python package (`webllm/`) that connects to an existing, logged-in Chromium over CDP and submits questions to LLM web UIs (DeepSeek/Qwen/Kimi/Wenxin). It returns structured JSON by default: answer text, citation/source links, session URL, timing, and per-question errors. `main.py` is a thin entrypoint shim. `README.md` is the user-facing doc.

## Commands
- Tests (must run from repo root): `.venv\Scripts\python -m pytest -q`
- Single test: `.venv\Scripts\python -m pytest tests/test_service.py::test_name -q`
- Run CLI: `.venv\Scripts\python main.py --provider deepseek --question "..."` (requires a CDP browser at `HERMES_CDP_URL`, default `http://127.0.0.1:9222`).
- Health check only: `.venv\Scripts\python main.py --provider deepseek --check --pretty`
- List providers: `.venv\Scripts\python -m webllm --list-providers --pretty`
- `.venv` is Python 3.11; system `python` is 3.13. No lint/typecheck/formatter config and no CI; pytest is the only automated verification. `Pillow` is required for baseline image diffs; the code degrades to byte comparison if it is missing.

## Architecture / gotchas
- `webllm/models.py`: `Source`, `Answer`, `BatchResult` and JSON serialization. `Answer.error_code` + `diagnostics` carry typed failures.
- `webllm/errors.py`: `WebLLMError(code, message, state, screenshot, diagnostics)`. Codes: `login_required`, `captcha_required`, `rate_limited`, `popup_blocking`, `ui_changed`, `answer_not_detected`, `page_not_ready`.
- `webllm/states.py`: `PageState` enum, `NEEDS_HUMAN_STATES`, `STATE_ERROR_CODES`.
- `webllm/diagnostics.py`: `HealthCheckConfig`, `PageHealthReport`, popup detection/dismissal, viewport screenshot + masked Pillow diff, baseline read/write under `.webllm/baselines/<provider>-{small,large}.png` (tracked in git; `.webllm/screenshots/` is gitignored).
- `webllm/input.py`: TXT/CSV/JSON/stdin question loading and the `__new_session__` marker.
- `webllm/providers/base.py`: `ProviderSpec`, base `WebProvider` (selectors, state detection, answer fingerprint, submit, response wait, clipboard capture, source extraction, new session).
- `webllm/providers/{deepseek,qwen,kimi,wenxin,antafu}.py`: one adapter/spec per web UI; override base methods for provider-specific behaviour. Register new providers in `webllm/providers/__init__.py`. Antafu (蚂蚁阿福) renders answers as `div.markdown-card.web-markdown-card` wrapping the markdown body `div.afu-markdown.mha-markdown-xui` (match `[class*='mha-markdown-xui']`); its send button has no label (match `button[class*='sendButton']`) and new chat is `button:has-text('开启新对话')`. Its academic citations are `span.custom-rich-text-refer` with no href, so `sources` is normally empty. Do NOT use `[class*='login']` for login detection: the empty-state element `loginEmptyText-*` matches it and causes a false `logged_out`; use `text=点击登录` / `[class*='loginModal']` instead. Its modes (深度搜索/健康问答/报告解读/药盒识别) are `div[class*='functionItem']` with the active one marked `activeFunction-*`, and are only clickable on the new-chat screen; `--mode` forces a new session and `AntafuProvider.select_mode` clicks the item. The 报告解读/药盒识别 modes upload files via a hidden `input[type=file]` (accept image/PDF); `spec.file_input_selectors` + `WebProvider.attach_files` handle `--file`, and Antafu's override waits for the `fileItem-*` preview. A text question is still required to enable the send button.
- `webllm/browser.py`: `BrowserSession` connects with `connect_over_cdp`, reuses a matching tab per provider, opens a new tab only when needed, and never launches/closes the browser. `close_created_pages()` closes only tabs created by this run.
- `webllm/service.py`: `WebLLMClient` keeps one CDP connection and one page per provider. `check()` returns a `PageHealthReport`; `ask()` raises `WebLLMError`; `ask_many()` catches per-question errors into `Answer.error`/`error_code` and stops by default. Preflight (state + popups + UI baseline) runs once per provider unless forced. Before each submit it calls `provider.prepare_for_question(page)` (base no-op). `AskOptions.mode` forces a new session and calls `provider.select_mode(page, mode)` right after `start_new_session`, then `provider.attach_files(page, paths)` when `AskOptions.attachments` is set (both base defaults raise; Antafu overrides).
- `webllm/cli.py`: JSON stdout (logs to stderr), exit codes `0` success, `1` runtime/partial failure, `2` input/argument error, `3` needs human (login/CAPTCHA/blocking popup).
- Answer capture: hover the last answer bubble, click its copy button, read the clipboard over CDP, fall back to the bubble's `inner_text`. Clipboard requires a headful browser.
- Response completion: wait for an answer fingerprint change first, then wait for a stop-generating button to hide, falling back to DOM mutation idle.
- UI baseline screenshots temporarily resize the viewport, mask `dynamic_selectors`, and are compared with Pillow; a missing baseline is created automatically.
- Source extraction scopes to `source_scope_selectors` (falling back to the last answer bubble), keeps only external HTTP(S) links, and deduplicates by URL. Non-anchor citations work through `source_item_selectors` + a provider `_build_source` override (Wenxin parses `data-long-press-ext-info`). It is best-effort.
- Do not auto-toggle web search or bypass login/CAPTCHA; the agent owns the browser state. Exception: DeepSeek's `prepare_for_question` enables the "深度思考" (DeepThink) toggle when it is off, detected via `div.ds-toggle-button` + `aria-pressed`/`ds-toggle-button--selected`.

## Repo conventions
- Design docs live in `docs/superpowers/specs/`; implementation plans in `docs/superpowers/plans/` use checkbox task lists with a "For agentic workers" header.
- `.playwright-profile/` is a git-tracked Chromium profile from the old launch-based flow; do not include its binary churn in commits.
- Tests never launch a browser or connect to CDP. They use local fake page/locator/session/provider classes and `monkeypatch`; follow that style.
- Questions, README, and user-facing strings are UTF-8; keep UTF-8 when editing.
