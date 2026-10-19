from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from webllm.input import (
    NEW_SESSION_MARKER,
    is_session_break_marker,
    load_questions,
)


def test_load_txt_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "questions.txt"
    path.write_text("第一个问题？\n\n第二个问题？\n", encoding="utf-8")

    assert load_questions(path) == ["第一个问题？", "第二个问题？"]


def test_load_csv_prefers_question_column(tmp_path: Path) -> None:
    path = tmp_path / "questions.csv"
    path.write_text("id,question\n1,第一个问题？\n2,第二个问题？\n", encoding="utf-8")

    assert load_questions(path) == ["第一个问题？", "第二个问题？"]


def test_load_csv_falls_back_to_first_column(tmp_path: Path) -> None:
    path = tmp_path / "questions.csv"
    path.write_text("第一个问题？,extra\n第二个问题？,extra\n", encoding="utf-8")

    assert load_questions(path) == ["第一个问题？", "第二个问题？"]


def test_load_json_accepts_strings_and_objects(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {"questions": ["第一个问题？", {"question": "第二个问题？", "id": 2}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert load_questions(path) == ["第一个问题？", "第二个问题？"]


def test_load_from_stdin_json(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(["问题一", "问题二"])))

    assert load_questions("-") == ["问题一", "问题二"]


def test_load_from_stdin_lines(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("问题一\n\n问题二\n"))

    assert load_questions("-") == ["问题一", "问题二"]


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_questions(tmp_path / "missing.txt")


def test_load_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "questions.md"
    path.write_text("question", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        load_questions(path)


def test_empty_input_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No valid questions"):
        load_questions(path)


def test_session_break_marker() -> None:
    assert is_session_break_marker(NEW_SESSION_MARKER)
    assert is_session_break_marker(f"  {NEW_SESSION_MARKER}  ")
    assert not is_session_break_marker("__new_session__ extra")
