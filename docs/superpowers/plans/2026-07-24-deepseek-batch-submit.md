# DeepSeek Batch Submit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Playwright CLI that reads questions from TXT or CSV files, lets the user log in to DeepSeek manually, and submits each question in sequence without saving answers.

**Architecture:** Keep the initial implementation compact but testable. `main.py` owns CLI orchestration, input parsing, and Playwright automation through small functions with clear boundaries. Local unit tests cover deterministic file parsing and argument-independent behavior, while live DeepSeek submission is manually verified.

**Tech Stack:** Python 3, Playwright for Python, pytest.

---

## File Structure

- `main.py`: CLI entry point, TXT/CSV question loading, Playwright launch and submission logic.
- `requirements.txt`: Runtime and test dependencies.
- `questions.example.txt`: TXT input example.
- `questions.example.csv`: CSV input example with a `question` column.
- `README.md`: Setup, usage, browser install, input formats, and safety notes.
- `tests/test_input_loader.py`: Unit tests for TXT and CSV parsing behavior.
- `docs/superpowers/specs/2026-07-24-deepseek-batch-submit-design.md`: Approved design.
- `docs/superpowers/plans/2026-07-24-deepseek-batch-submit.md`: This implementation plan.

### Task 1: Project Dependencies And Input Parsing Tests

**Files:**
- Create: `requirements.txt`
- Create: `tests/test_input_loader.py`
- Modify: `main.py`

- [ ] **Step 1: Create dependency list**

Create `requirements.txt`:

```text
playwright>=1.45.0
pytest>=8.0.0
```

- [ ] **Step 2: Write failing TXT parsing test**

Create `tests/test_input_loader.py` with:

```python
from pathlib import Path

from main import load_questions


def test_load_questions_from_txt_skips_blank_lines(tmp_path: Path) -> None:
    input_file = tmp_path / "questions.txt"
    input_file.write_text("第一题是什么？\n\n  第二题是什么？  \n", encoding="utf-8")

    assert load_questions(input_file) == ["第一题是什么？", "第二题是什么？"]
```

- [ ] **Step 3: Run TXT parsing test and verify failure**

Run:

```bash
python -m pytest tests/test_input_loader.py::test_load_questions_from_txt_skips_blank_lines -v
```

Expected: FAIL because `main.py` or `load_questions` does not exist yet.

- [ ] **Step 4: Implement minimal TXT loader**

Create `main.py` with:

```python
from pathlib import Path


def load_questions(input_path: Path) -> list[str]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() != ".txt":
        raise ValueError("Unsupported input file type. Use .txt or .csv.")

    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
```

- [ ] **Step 5: Run TXT parsing test and verify pass**

Run:

```bash
python -m pytest tests/test_input_loader.py::test_load_questions_from_txt_skips_blank_lines -v
```

Expected: PASS.

- [ ] **Step 6: Add CSV parsing tests**

Append to `tests/test_input_loader.py`:

```python
def test_load_questions_from_csv_prefers_question_column(tmp_path: Path) -> None:
    input_file = tmp_path / "questions.csv"
    input_file.write_text(
        "id,question,notes\n1,什么是 Playwright?,keep\n2,,skip\n3,如何批量提交问题?,keep\n",
        encoding="utf-8",
    )

    assert load_questions(input_file) == ["什么是 Playwright?", "如何批量提交问题?"]


def test_load_questions_from_csv_falls_back_to_first_column(tmp_path: Path) -> None:
    input_file = tmp_path / "questions.csv"
    input_file.write_text(
        "第一题是什么？,tag-a\n\n第二题是什么？,tag-b\n",
        encoding="utf-8",
    )

    assert load_questions(input_file) == ["第一题是什么？", "第二题是什么？"]
```

- [ ] **Step 7: Run CSV parsing tests and verify failure**

Run:

```bash
python -m pytest tests/test_input_loader.py -v
```

Expected: FAIL because `.csv` support is not implemented.

- [ ] **Step 8: Implement CSV loader**

Replace `main.py` content with:

```python
import csv
from pathlib import Path


def load_questions(input_path: Path) -> list[str]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return load_txt_questions(path)
    if suffix == ".csv":
        return load_csv_questions(path)

    raise ValueError("Unsupported input file type. Use .txt or .csv.")


def load_txt_questions(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_csv_questions(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        has_header = csv.Sniffer().has_header(sample) if sample.strip() else False

        if has_header:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or []
            column_name = "question" if "question" in fieldnames else fieldnames[0]
            return [
                value.strip()
                for row in reader
                for value in [row.get(column_name, "")]
                if value and value.strip()
            ]

        reader = csv.reader(file)
        return [
            row[0].strip()
            for row in reader
            if row and row[0].strip()
        ]
```

- [ ] **Step 9: Run parsing tests and verify pass**

Run:

```bash
python -m pytest tests/test_input_loader.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit parsing foundation**

Run:

```bash
git add main.py requirements.txt tests/test_input_loader.py
git commit -m "feat: add input parsing foundation"
```

Expected: Commit succeeds.

### Task 2: CLI And DeepSeek Playwright Automation

**Files:**
- Modify: `main.py`
- Modify: `tests/test_input_loader.py`

- [ ] **Step 1: Add empty-input test**

Append to `tests/test_input_loader.py`:

```python
def test_load_questions_rejects_empty_file(tmp_path: Path) -> None:
    input_file = tmp_path / "questions.txt"
    input_file.write_text("\n\n", encoding="utf-8")

    try:
        load_questions(input_file)
    except ValueError as exc:
        assert "No valid questions found" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty input file")
```

- [ ] **Step 2: Run empty-input test and verify failure**

Run:

```bash
python -m pytest tests/test_input_loader.py::test_load_questions_rejects_empty_file -v
```

Expected: FAIL because empty input is currently accepted.

- [ ] **Step 3: Implement empty-input validation and CLI automation**

Replace `main.py` with:

```python
import argparse
import csv
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright


DEFAULT_DEEPSEEK_URL = "https://chat.deepseek.com/"
INPUT_SELECTORS = [
    "textarea",
    "[contenteditable='true']",
    "div[role='textbox']",
]


def load_questions(input_path: Path) -> list[str]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        questions = load_txt_questions(path)
    elif suffix == ".csv":
        questions = load_csv_questions(path)
    else:
        raise ValueError("Unsupported input file type. Use .txt or .csv.")

    if not questions:
        raise ValueError(f"No valid questions found in: {path}")

    return questions


def load_txt_questions(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_csv_questions(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        has_header = csv.Sniffer().has_header(sample) if sample.strip() else False

        if has_header:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or []
            if not fieldnames:
                return []
            column_name = "question" if "question" in fieldnames else fieldnames[0]
            return [
                value.strip()
                for row in reader
                for value in [row.get(column_name, "")]
                if value and value.strip()
            ]

        reader = csv.reader(file)
        return [
            row[0].strip()
            for row in reader
            if row and row[0].strip()
        ]


def find_message_input(page: Page):
    for selector in INPUT_SELECTORS:
        locator = page.locator(selector).last
        try:
            locator.wait_for(state="visible", timeout=3000)
            return locator
        except PlaywrightError:
            continue
    raise RuntimeError("Could not find the DeepSeek message input box after login.")


def submit_question(page: Page, question: str) -> None:
    message_input = find_message_input(page)
    message_input.fill(question)
    message_input.press("Enter")


def run_batch(url: str, questions: list[str], delay: float) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")

        input("Please log in to DeepSeek in the opened browser, then press Enter here to continue...")

        for index, question in enumerate(questions, start=1):
            print(f"[{index}/{len(questions)}] Submitting: {question}")
            submit_question(page, question)
            page.wait_for_timeout(delay * 1000)

        print("Batch submission finished. The browser will remain open until you press Enter.")
        input("Press Enter to close the browser...")
        browser.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-submit questions to DeepSeek web UI with Playwright."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to .txt or .csv file.")
    parser.add_argument(
        "--delay",
        default=5.0,
        type=float,
        help="Seconds to wait after each submission. Default: 5.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_DEEPSEEK_URL,
        help=f"DeepSeek URL. Default: {DEFAULT_DEEPSEEK_URL}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        questions = load_questions(args.input)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Loaded {len(questions)} question(s) from {args.input}")
    run_batch(args.url, questions, args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run unit tests and verify pass**

Run:

```bash
python -m pytest tests/test_input_loader.py -v
```

Expected: PASS.

- [ ] **Step 5: Run CLI help**

Run:

```bash
python main.py --help
```

Expected: CLI help shows `--input`, `--delay`, and `--url`.

- [ ] **Step 6: Commit CLI automation**

Run:

```bash
git add main.py tests/test_input_loader.py
git commit -m "feat: add deepseek batch submission cli"
```

Expected: Commit succeeds.

### Task 3: Examples, README, And Final Verification

**Files:**
- Create: `questions.example.txt`
- Create: `questions.example.csv`
- Create: `README.md`
- Modify: `docs/superpowers/plans/2026-07-24-deepseek-batch-submit.md`

- [ ] **Step 1: Add example TXT input**

Create `questions.example.txt`:

```text
请用三句话解释 Playwright 是什么。
请给我一个 Python 自动化测试的入门学习路线。
```

- [ ] **Step 2: Add example CSV input**

Create `questions.example.csv`:

```csv
question
请用三句话解释 DeepSeek 的网页端适合哪些使用场景。
请给我一个批量整理问题清单的建议。
```

- [ ] **Step 3: Add README**

Create `README.md`:

```markdown
# DeepSeek Batch Submit

This project uses Playwright for Python to batch-submit questions to the DeepSeek web UI.

It reads questions from `.txt` or `.csv`, opens a visible Chromium browser, waits for you to log in manually, then submits each question in sequence. It does not read or save answers.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Input Formats

TXT:

```text
第一题是什么？
第二题是什么？
```

CSV with a `question` column:

```csv
question
第一题是什么？
第二题是什么？
```

CSV without a `question` column reads the first column.

## Usage

```bash
python main.py --input questions.example.txt
```

Optional arguments:

```bash
python main.py --input questions.example.csv --delay 8
python main.py --input questions.example.txt --url https://chat.deepseek.com/
```

## Notes

- The browser opens in headed mode so you can log in manually each run.
- After login, return to the terminal and press Enter to start submitting.
- Keep a reasonable delay between submissions.
- If DeepSeek changes its web UI, update the selectors in `INPUT_SELECTORS` inside `main.py`.
- This tool does not bypass login, CAPTCHA, rate limits, or site protections.
```

- [ ] **Step 4: Run all tests**

Run:

```bash
python -m pytest -v
```

Expected: PASS.

- [ ] **Step 5: Run CLI help**

Run:

```bash
python main.py --help
```

Expected: CLI help renders successfully.

- [ ] **Step 6: Commit docs and examples**

Run:

```bash
git add README.md questions.example.txt questions.example.csv docs/superpowers/plans/2026-07-24-deepseek-batch-submit.md
git commit -m "docs: add usage guide and examples"
```

Expected: Commit succeeds.

- [ ] **Step 7: Manual verification instructions**

Run after installing Playwright browsers:

```bash
python main.py --input questions.example.txt --delay 8
```

Expected:

- Chromium opens at DeepSeek.
- User logs in manually.
- Pressing Enter in the terminal starts submission.
- Two example questions are submitted one at a time.
- No answer files are created.

## Self-Review

- Spec coverage: The plan covers CSV/TXT input, manual login, sequential submission, no answer saving, configurable delay, URL override, examples, README, and local tests.
- Placeholder scan: No placeholders are intentionally left for implementation.
- Type consistency: The plan consistently uses `Path`, `list[str]`, `load_questions`, `load_txt_questions`, `load_csv_questions`, `run_batch`, and `submit_question`.
