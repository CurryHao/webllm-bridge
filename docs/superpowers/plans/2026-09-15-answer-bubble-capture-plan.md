# Answer Bubble Capture Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each answer finishes, capture the answer bubble's visible DOM text and save it to a file, so a batch run produces a Q/A transcript.

**Architecture:** Add an `answer_selectors` tuple to `ProviderConfig` (shared `COMMON_ANSWER_SELECTORS` for all providers, ordered specific-to-generic). `capture_answer_text(page)` returns the stripped `inner_text` of the last element matching the first selector that yields a non-empty result, or `None`. `run_batch` accepts an `answers_out` path and appends one numbered `[index] question` block per answer after `wait_for_response_complete`; blocks end with a `---` separator line so they can be split reliably later. The CLI defaults the output to `<input stem>.answers.txt` next to the input file, with `--answers-out` to override and `--no-answers` to disable.

**Tech Stack:** Python 3.13, Playwright, pytest

---

### Task 1: Capture the answer bubble text

**Files:**
- Modify: `main.py`
- Modify: `tests/test_input_loader.py`

- [x] **Step 1: Write the failing tests** — `capture_answer_text` returns the first matching non-empty bubble's stripped text, skips unreadable/empty bubbles, and returns `None` when no selector matches.
- [x] **Step 2: Verify failure** — `AttributeError: module 'main' has no attribute 'capture_answer_text'`.
- [x] **Step 3: Implement** — `COMMON_ANSWER_SELECTORS` (assistant data-attributes/classes first, `div[class*='message']` as last resort), `answer_selectors` field on `ProviderConfig` for all four providers, and `capture_answer_text(page)`.
- [x] **Step 4: Verify pass.**

### Task 2: Save captured answers to a file

**Files:**
- Modify: `main.py`
- Modify: `tests/test_input_loader.py`

- [x] **Step 1: Write the failing tests** — `append_answer` writes numbered `[index] question` blocks; `run_batch` with `answers_out` saves captured text after each wait and saves an `(answer text not captured)` placeholder when capture returns `None`; `main()` defaults the output next to the input file and `--no-answers` disables it.
- [x] **Step 2: Verify failure** — missing `append_answer`, `run_batch` rejects `answers_out`, argparse rejects `--no-answers`.
- [x] **Step 3: Implement** — `append_answer(answers_out, index, question, answer_text)` appends in UTF-8; `run_batch` gains `answers_out: Path | None = None` and captures right after `wait_for_response_complete`; `parse_args` gains `--answers-out` / `--no-answers`; `main()` computes the default path.
- [x] **Step 4: Verify pass.**

### Task 3: Documentation

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update the intro** — the tool now reads and saves answer text instead of not touching answers.
- [x] **Step 2: Document the new flags** — default output location, `--answers-out`, `--no-answers`, and the selector update note.
- [x] **Step 3: Run the full test suite** — all tests pass.
