# New Session Marker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let CSV input include a `__new_session__` row that triggers a fresh chat session before continuing with later questions.

**Architecture:** Preserve the raw CSV row values so the runner can distinguish normal questions from session-break markers. Add a small session-switch helper in `main.py` that clicks the provider's new-session control, then keep the existing submit-and-wait flow unchanged for normal questions.

**Tech Stack:** Python 3.13, Playwright, pytest

---

### Task 1: Preserve session markers from CSV input

**Files:**
- Modify: `main.py`
- Modify: `tests/test_input_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_load_questions_from_csv_preserves_session_marker(tmp_path: Path) -> None:
    input_file = tmp_path / "questions.csv"
    input_file.write_text(
        "question\n第一组问题1\n__new_session__\n第二组问题1\n",
        encoding="utf-8",
    )

    assert load_questions(input_file) == ["第一组问题1", "__new_session__", "第二组问题1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_input_loader.py -k session_marker`
Expected: FAIL because the CSV loader currently filters the marker out.

- [ ] **Step 3: Write minimal implementation**

```python
def load_csv_questions(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = [
            [cell.strip() for cell in row]
            for row in csv.reader(file)
            if row and any(cell.strip() for cell in row)
        ]

    if not rows:
        return []

    header = rows[0]
    if "question" in header:
        column_index = header.index("question")
        data_rows = rows[1:]
    else:
        column_index = 0
        data_rows = rows

    return [
        row[column_index].strip()
        for row in data_rows
        if len(row) > column_index and row[column_index].strip()
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_input_loader.py -k session_marker`
Expected: PASS.

### Task 2: Switch sessions when the marker is encountered

**Files:**
- Modify: `main.py`
- Modify: `tests/test_input_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_run_batch_switches_session_on_marker(monkeypatch) -> None:
    events: list[str] = []

    class FakePage:
        def goto(self, url: str, wait_until: str) -> None:
            events.append("goto")

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

        def close(self) -> None:
            events.append("close")

    class FakeChromium:
        def launch(self, headless: bool) -> FakeBrowser:
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        def __enter__(self) -> FakePlaywright:
            return FakePlaywright()

        def __exit__(self, *args) -> None:
            return None

    monkeypatch.setattr(main, "sync_playwright", lambda: FakePlaywrightContext())
    monkeypatch.setattr("builtins.input", lambda prompt="": events.append("input") or "")
    monkeypatch.setattr(main, "submit_question", lambda page, question: events.append(f"submit:{question}"))
    monkeypatch.setattr(main, "wait_for_response_complete", lambda page, timeout: events.append(f"wait:{timeout}"))
    monkeypatch.setattr(main, "start_new_session", lambda page: events.append("new-session"))

    main.run_batch("https://example.test/", ["第一题", "__new_session__", "第二题"], 0, response_timeout=120)

    assert events == ["goto", "input", "submit:第一题", "wait:120", "new-session", "submit:第二题", "wait:120", "input", "close"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_input_loader.py -k session_switch`
Expected: FAIL because `run_batch` currently treats the marker like a normal question.

- [ ] **Step 3: Write minimal implementation**

```python
NEW_SESSION_MARKER = "__new_session__"

def start_new_session(page: Page) -> None:
    for selector in NEW_SESSION_BUTTON_SELECTORS:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=3000)
            locator.click()
            return
        except PlaywrightError:
            continue
    raise RuntimeError("Could not find the new session button.")

def run_batch(...):
    ...
    for index, question in enumerate(questions, start=1):
        if question == NEW_SESSION_MARKER:
            start_new_session(page)
            continue
        print(f"[{index}/{len(questions)}] Submitting: {question}")
        submit_question(page, question)
        wait_for_response_complete(page, response_timeout)
        page.wait_for_timeout(delay * 1000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_input_loader.py -k session_switch`
Expected: PASS.

### Task 3: Add real new-session selectors and docs

**Files:**
- Modify: `main.py`
- Modify: `README.md`

- [ ] **Step 1: Add provider selectors**

```python
NEW_SESSION_BUTTON_SELECTORS = [
    "button:has-text('新会话')",
    "button:has-text('新聊天')",
    "button[aria-label*='新会话']",
    "button[aria-label*='New chat']",
    "button:has-text('New chat')",
]
```

- [ ] **Step 2: Document the marker row**

```markdown
Use `__new_session__` on its own CSV row to start a fresh chat before the next question.
```

- [ ] **Step 3: Run the full test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: All tests pass.
