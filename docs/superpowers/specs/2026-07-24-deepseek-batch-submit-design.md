# DeepSeek Batch Submit Design

## Goal

Build a lightweight Python CLI tool that uses Playwright to automate the DeepSeek web UI. The tool reads questions from CSV or TXT files, opens the DeepSeek chat page, lets the user log in manually, then submits each question in sequence.

The tool does not read, parse, or save DeepSeek responses.

## User Workflow

1. Install dependencies.
2. Prepare a `questions.txt` or `questions.csv` input file.
3. Run the CLI with an input path.
4. A Chromium browser opens at the DeepSeek web app.
5. The user completes login manually.
6. The user returns to the terminal and presses Enter.
7. The tool submits each question one by one.
8. The browser remains open at the end so the user can inspect the session.

## Input Rules

TXT input:

- One question per non-empty line.
- Blank lines are ignored.

CSV input:

- If a `question` column exists, the tool reads that column.
- Otherwise, the tool reads the first column.
- Empty values are ignored.

## Architecture

The project will be a small Python package-style CLI without unnecessary framework overhead.

Core units:

- `main.py`: CLI entry point, argument parsing, high-level orchestration.
- Input loader functions: read and normalize TXT or CSV question lists.
- Playwright automation functions: open DeepSeek, wait for manual login confirmation, submit each question.
- Example input files and README documentation.

The first implementation can keep the code in `main.py` while preserving clear function boundaries. If the tool grows later, input loading and browser automation can be split into separate modules.

## Browser Automation

The automation flow uses Playwright for Python:

- Launch Chromium in headed mode.
- Navigate to `https://chat.deepseek.com/`.
- Wait for the user to log in manually and press Enter in the terminal.
- Locate the message input area.
- Fill each question and submit it.
- Wait a configurable delay after each submission.

Selectors should be centralized in code so they can be updated easily if DeepSeek changes its UI.

## CLI

Expected command:

```bash
python main.py --input questions.txt
```

Useful options:

- `--input`: Required path to `.txt` or `.csv`.
- `--delay`: Seconds to wait after each submission. Default: `5`.
- `--url`: DeepSeek URL. Default: `https://chat.deepseek.com/`.

## Error Handling

The tool should fail with clear messages when:

- The input file does not exist.
- The input extension is not `.txt` or `.csv`.
- No valid questions are found.
- The DeepSeek input box cannot be located after login.

During batch submission, a failed question should be reported in the terminal with its index. The initial version may stop on browser automation errors because continuing blindly could submit the wrong content.

## Testing

Automated tests should focus on deterministic local behavior:

- TXT parsing skips blank lines and preserves question text.
- CSV parsing prefers the `question` column when present.
- CSV parsing falls back to the first column when no `question` column exists.

End-to-end submission against DeepSeek is an external browser workflow. It should be verified manually after implementation because it depends on live site state, login, network conditions, and current UI selectors.

## Out Of Scope

- Saving answers.
- Reading generated responses.
- Multi-account support.
- Automatic login.
- CAPTCHA or anti-bot bypass.
- Parallel submission.
- Browser session persistence.
