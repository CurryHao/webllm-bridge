from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO

NEW_SESSION_MARKER = "__new_session__"


def is_session_break_marker(question: str) -> bool:
    return question.strip() == NEW_SESSION_MARKER


def load_questions(input_path: Path | str) -> list[str]:
    if str(input_path) == "-":
        return _load_stream(sys.stdin, "stdin")

    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        questions = _load_lines(path.read_text(encoding="utf-8").splitlines())
    elif suffix == ".csv":
        questions = _load_csv(path)
    elif suffix == ".json":
        questions = _load_json(path.read_text(encoding="utf-8-sig"))
    else:
        raise ValueError("Unsupported input file type. Use .txt, .csv, or .json.")

    if not questions:
        raise ValueError(f"No valid questions found in: {path}")

    return questions


def _load_stream(stream: TextIO, name: str) -> list[str]:
    text = stream.read().strip()
    if not text:
        raise ValueError(f"No valid questions found in: {name}")

    if text.startswith("[") or text.startswith("{"):
        questions = _load_json(text)
    else:
        questions = _load_lines(text.splitlines())

    if not questions:
        raise ValueError(f"No valid questions found in: {name}")
    return questions


def _load_lines(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _load_csv(path: Path) -> list[str]:
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


def _load_json(text: str) -> list[str]:
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON question input: {exc}") from exc

    if isinstance(payload, dict):
        payload = payload.get("questions", [])

    if not isinstance(payload, list):
        raise ValueError("JSON question input must be a list or an object with a 'questions' list.")

    questions: list[str] = []
    for item in payload:
        if isinstance(item, str):
            question = item.strip()
        elif isinstance(item, dict):
            question = str(item.get("question", "")).strip()
        else:
            question = ""
        if question:
            questions.append(question)
    return questions
