from __future__ import annotations

import json
from pathlib import Path

import pytest

from webllm import cli
from webllm.diagnostics import PageHealthReport
from webllm.models import Answer, BatchResult, Source
from webllm.service import AskOptions
from webllm.states import PageState


class FakeClient:
    calls: list[dict[str, object]] = []
    fail = False
    needs_human = False

    def __init__(self, cdp_url: str, *, health=None) -> None:
        self.cdp_url = cdp_url
        self.health = health

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def check(self, provider: str):
        return PageHealthReport(provider=provider, state=PageState.READY)

    def ask_many(self, provider: str, questions: list[str], *, options: AskOptions):
        FakeClient.calls.append(
            {"provider": provider, "questions": questions, "options": options, "cdp_url": self.cdp_url}
        )
        if FakeClient.fail:
            raise RuntimeError("boom")
        if FakeClient.needs_human:
            return BatchResult(
                provider=provider,
                display_name="DeepSeek",
                results=[
                    Answer(
                        provider=provider,
                        question=questions[0],
                        error="WebLLMError: login required",
                        error_code="login_required",
                    )
                ],
            )
        return BatchResult(
            provider=provider,
            display_name="DeepSeek",
            session_url="https://chat.deepseek.com/a/chat/1",
            elapsed_seconds=1.25,
            results=[
                Answer(
                    provider=provider,
                    question=questions[0],
                    answer="答案",
                    sources=[Source(url="https://example.com/source", title="来源")],
                    session_url="https://chat.deepseek.com/a/chat/1",
                    elapsed_seconds=1.25,
                    captured_by="copy",
                )
            ],
        )


@pytest.fixture(autouse=True)
def reset_fake_client() -> None:
    FakeClient.calls = []
    FakeClient.fail = False
    FakeClient.needs_human = False


def run_cli(argv: list[str]) -> int:
    return cli.main(argv, client_factory=FakeClient)


def test_list_providers_outputs_json(capsys) -> None:
    assert run_cli(["--list-providers"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {provider["name"] for provider in payload["providers"]} == {
        "deepseek",
        "qwen",
        "kimi",
        "wenxin",
        "antafu",
    }


def test_question_outputs_json_result(capsys) -> None:
    assert run_cli(["--provider", "deepseek", "-q", "问题"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "deepseek"
    assert payload["results"][0]["answer"] == "答案"
    assert payload["results"][0]["sources"][0]["url"] == "https://example.com/source"
    assert FakeClient.calls[0]["questions"] == ["问题"]
    assert FakeClient.calls[0]["cdp_url"] == "http://127.0.0.1:9222"


def test_questions_can_be_combined_from_input_file(tmp_path: Path, capsys) -> None:
    path = tmp_path / "questions.txt"
    path.write_text("文件问题\n", encoding="utf-8")

    assert run_cli(["-q", "命令行问题", "--input", str(path)]) == 0
    capsys.readouterr()

    assert FakeClient.calls[0]["questions"] == ["命令行问题", "文件问题"]


def test_missing_questions_returns_structured_error(capsys) -> None:
    assert run_cli([]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "input_error"


def test_missing_attachment_returns_input_error(tmp_path: Path, capsys) -> None:
    assert run_cli(["-q", "问题", "--file", str(tmp_path / "nope.png")]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "input_error"


def test_mode_and_file_are_forwarded(tmp_path: Path, capsys) -> None:
    image = tmp_path / "report.png"
    image.write_bytes(b"png")

    assert run_cli(["-q", "问题", "--mode", "report", "--file", str(image)]) == 0
    capsys.readouterr()

    options = FakeClient.calls[0]["options"]
    assert options.mode == "report"
    assert options.attachments == [str(image)]


def test_client_error_returns_structured_error(capsys) -> None:
    FakeClient.fail = True

    assert run_cli(["-q", "问题"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "boom"


def test_options_are_forwarded(capsys) -> None:
    assert (
        run_cli(
            [
                "--provider",
                "kimi",
                "--cdp-url",
                "http://localhost:9333",
                "--timeout",
                "42",
                "--delay",
                "2",
                "--new-session",
                "--no-sources",
                "--continue-on-error",
                "--close-pages",
                "--no-preflight",
                "--ui-check",
                "error",
                "--ui-viewport",
                "small",
                "--ui-diff-threshold",
                "0.1",
                "--no-dismiss-popups",
                "--wait-human",
                "5",
                "--preflight-timeout",
                "12",
                "-q",
                "问题",
            ]
        )
        == 0
    )
    capsys.readouterr()

    call = FakeClient.calls[0]
    options = call["options"]
    assert call["provider"] == "kimi"
    assert call["cdp_url"] == "http://localhost:9333"
    assert options.timeout == 42
    assert options.delay == 2
    assert options.new_session is True
    assert options.capture_sources is False
    assert options.stop_on_error is False
    assert options.close_pages is True
    assert options.preflight is False
    assert options.wait_human == 5
    assert options.preflight_timeout == 12
    assert options.health.ui_check == "error"
    assert options.health.viewports == ("small",)
    assert options.health.diff_threshold == 0.1
    assert options.health.dismiss_popups is False


def test_check_outputs_health(capsys) -> None:
    assert run_cli(["--check"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["health"]["state"] == "ready"
    assert FakeClient.calls == []


def test_needs_human_returns_exit_3(capsys) -> None:
    FakeClient.needs_human = True

    assert run_cli(["-q", "问题"]) == 3

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["needs_human"] is True
    assert payload["results"][0]["error_code"] == "login_required"


def test_answers_out_appends_text(tmp_path: Path, capsys) -> None:
    answers_path = tmp_path / "answers.txt"

    assert run_cli(["-q", "问题", "--answers-out", str(answers_path)]) == 0
    capsys.readouterr()

    assert answers_path.read_text(encoding="utf-8") == "[1] 问题\n答案\n---\n\n"


def test_text_format_prints_answer_and_sources(capsys) -> None:
    assert run_cli(["-q", "问题", "--format", "text"]) == 0

    output = capsys.readouterr().out
    assert "[1] 问题" in output
    assert "答案" in output
    assert "https://example.com/source" in output
