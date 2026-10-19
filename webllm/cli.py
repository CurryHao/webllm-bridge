from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from webllm import __version__
from webllm.diagnostics import (
    DEFAULT_BASELINE_DIR,
    DEFAULT_SCREENSHOT_DIR,
    HealthCheckConfig,
    resolve_viewports,
)
from webllm.errors import WebLLMError
from webllm.input import load_questions
from webllm.models import NEEDS_HUMAN_CODES, BatchResult
from webllm.providers import PROVIDERS, list_providers
from webllm.service import AskOptions, WebLLMClient

DEFAULT_CDP_URL = "http://127.0.0.1:9222"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webllm",
        description=(
            "Agent-friendly bridge to LLM web UIs over an existing CDP browser. "
            "Outputs structured JSON by default."
        ),
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("WEBLLM_PROVIDER", "deepseek"),
        choices=sorted(PROVIDERS),
        help="Target web UI. Default: WEBLLM_PROVIDER or deepseek.",
    )
    parser.add_argument(
        "-q",
        "--question",
        action="append",
        default=[],
        help="Question to submit. Repeat for multiple questions.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Read questions from .txt, .csv, or .json. Use '-' for stdin.",
    )
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("WEBLLM_CDP_URL", DEFAULT_CDP_URL),
        help="Chromium CDP endpoint. Default: WEBLLM_CDP_URL or http://127.0.0.1:9222.",
    )
    parser.add_argument(
        "--timeout",
        default=300.0,
        type=float,
        help="Seconds to wait for each answer. Default: 300.",
    )
    parser.add_argument(
        "--delay",
        default=0.0,
        type=float,
        help="Seconds to wait after each answer. Default: 0.",
    )
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Start a fresh chat before the first question.",
    )
    parser.add_argument(
        "--mode",
        default=None,
        help=(
            "Conversation mode. Implies a new session. For antafu: "
            "deep_search|health_qa|report|medicine (or the Chinese labels)."
        ),
    )
    parser.add_argument(
        "--file",
        action="append",
        type=Path,
        default=[],
        help=(
            "Attach a local file (image/PDF) before asking. Repeatable. "
            "Used by antafu report/medicine modes."
        ),
    )
    parser.add_argument(
        "--no-sources",
        action="store_true",
        help="Skip citation/link extraction.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep asking remaining questions after a failure.",
    )
    parser.add_argument(
        "--close-pages",
        action="store_true",
        help="Close tabs created by this run when finished.",
    )
    parser.add_argument(
        "--answers-out",
        type=Path,
        default=None,
        help="Also append answers to a plain-text file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only run login/popup/UI health checks, then exit.",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip the login/popup/UI health check before asking.",
    )
    parser.add_argument(
        "--preflight-timeout",
        default=30.0,
        type=float,
        help="Seconds to wait for the page to become ready. Default: 30.",
    )
    parser.add_argument(
        "--wait-human",
        default=0.0,
        type=float,
        help="If >0, poll this many seconds for manual login/CAPTCHA instead of failing fast.",
    )
    parser.add_argument(
        "--ui-check",
        choices=("off", "warn", "error"),
        default="warn",
        help="Compare the page against its baseline. Default: warn.",
    )
    parser.add_argument(
        "--ui-viewport",
        choices=("small", "large", "both"),
        default="both",
        help="Viewports used for baseline comparison. Default: both.",
    )
    parser.add_argument(
        "--ui-diff-threshold",
        default=None,
        type=float,
        help="Override the per-provider changed-pixel ratio threshold.",
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=DEFAULT_BASELINE_DIR,
        help=f"Baseline image directory. Default: {DEFAULT_BASELINE_DIR}.",
    )
    parser.add_argument(
        "--screenshots-dir",
        type=Path,
        default=DEFAULT_SCREENSHOT_DIR,
        help=f"Evidence/diff image directory. Default: {DEFAULT_SCREENSHOT_DIR}.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite stored baselines with the current page.",
    )
    parser.add_argument(
        "--no-dismiss-popups",
        action="store_true",
        help="Report popups but do not try to close them.",
    )
    parser.add_argument(
        "--popup-error",
        choices=("warn", "error"),
        default="warn",
        help="Treat remaining popups as a blocking error. Default: warn.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="stdout format. Default: json.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Indent JSON output.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages on stderr.",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List supported providers and exit.",
    )
    parser.add_argument("--version", action="version", version=f"webllm {__version__}")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def build_health(args: argparse.Namespace) -> HealthCheckConfig:
    return HealthCheckConfig(
        baselines_dir=args.baseline_dir,
        screenshots_dir=args.screenshots_dir,
        viewports=resolve_viewports(args.ui_viewport),
        ui_check=args.ui_check,
        diff_threshold=args.ui_diff_threshold,
        update_baseline=args.update_baseline,
        dismiss_popups=not args.no_dismiss_popups,
        popup_error=args.popup_error,
    )


def main(
    argv: list[str] | None = None,
    *,
    client_factory: type[WebLLMClient] = WebLLMClient,
) -> int:
    _configure_utf8_stdio()
    args = parse_args(argv)

    if args.list_providers:
        payload = {"ok": True, "providers": list_providers()}
        _emit(payload, args)
        return 0

    health = build_health(args)

    if args.check:
        return _run_check(args, client_factory, health)

    try:
        questions = collect_questions(args)
    except (FileNotFoundError, ValueError) as exc:
        return _fail(args, "input_error", exc, 2)

    missing_files = [str(path) for path in args.file if not path.is_file()]
    if missing_files:
        return _fail(
            args, "input_error", ValueError(f"Attachment not found: {missing_files[0]}"), 2
        )

    options = AskOptions(
        timeout=args.timeout,
        delay=args.delay,
        capture_sources=not args.no_sources,
        new_session=args.new_session,
        mode=args.mode,
        attachments=[str(path) for path in args.file],
        close_pages=args.close_pages,
        stop_on_error=not args.continue_on_error,
        preflight=not args.no_preflight,
        preflight_timeout=args.preflight_timeout,
        wait_human=args.wait_human,
        health=health,
    )

    try:
        with client_factory(args.cdp_url, health=health) as client:
            result = client.ask_many(args.provider, questions, options=options)
    except WebLLMError as exc:
        return _fail_webllm(args, exc)
    except Exception as exc:
        return _fail(args, type(exc).__name__, exc, 1)

    if args.answers_out is not None:
        try:
            append_answers(args.answers_out, result)
        except OSError as exc:
            _log(args, f"Warning: could not write answers file: {exc}")

    _emit(result.to_dict(), args, result=result)
    if result.ok:
        return 0
    return 3 if result.needs_human else 1


def _run_check(
    args: argparse.Namespace,
    client_factory: type[WebLLMClient],
    health: HealthCheckConfig,
) -> int:
    try:
        with client_factory(args.cdp_url, health=health) as client:
            report = client.check(args.provider)
    except WebLLMError as exc:
        return _fail_webllm(args, exc)
    except Exception as exc:
        return _fail(args, type(exc).__name__, exc, 1)

    payload = {"ok": True, "provider": args.provider, "health": report.to_dict()}
    _emit(payload, args)
    return 0


def collect_questions(args: argparse.Namespace) -> list[str]:
    questions = [question.strip() for question in args.question if question.strip()]
    if args.input is not None:
        questions.extend(load_questions(args.input))
    if not questions:
        raise ValueError("No questions provided. Use --question or --input.")
    return questions


def append_answers(path: Path, result: BatchResult) -> None:
    with path.open("a", encoding="utf-8") as file:
        for index, answer in enumerate(result.results, start=1):
            if not answer.ok:
                continue
            file.write(f"[{index}] {answer.question}\n{answer.answer}\n---\n\n")


def _emit(payload: dict[str, Any], args: argparse.Namespace, *, result: BatchResult | None = None) -> None:
    if args.format == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(payload, ensure_ascii=False, indent=indent))
        return

    if "providers" in payload:
        for provider in payload["providers"]:
            print(f"{provider['name']}\t{provider['display_name']}\t{provider['url']}")
        return

    if "health" in payload:
        health = payload["health"]
        print(f"state: {health['state']}  needs_human: {health['needs_human']}")
        for popup in health.get("popups", []):
            print(f"popup: {popup['text'] or popup['class_name']}")
        for diff in health.get("ui_diffs", []):
            print(
                f"ui[{diff['viewport']}]: ratio={diff['diff_ratio']} "
                f"changed={diff['changed']} ({diff['baseline_action']})"
            )
        for warning in health.get("warnings", []):
            print(f"warning: {warning}")
        return

    if result is not None:
        for index, answer in enumerate(result.results, start=1):
            print(f"[{index}] {answer.question}")
            if answer.ok:
                print(answer.answer or "(empty answer)")
                if answer.sources:
                    print("Sources:")
                    for source in answer.sources:
                        title = source.title or source.url
                        print(f"- {title}\n  {source.url}")
            else:
                print(f"ERROR[{answer.error_code or 'error'}]: {answer.error}")
            print("---")


def _fail(
    args: argparse.Namespace,
    error_type: str,
    exc: Exception,
    exit_code: int,
) -> int:
    _log(args, f"Error: {exc}")
    payload = {
        "ok": False,
        "provider": args.provider,
        "error": {"type": error_type, "message": str(exc)},
        "results": [],
    }
    _emit(payload, args)
    return exit_code


def _fail_webllm(args: argparse.Namespace, exc: WebLLMError) -> int:
    _log(args, f"Error: {exc}")
    payload = {
        "ok": False,
        "provider": args.provider,
        "error": exc.to_dict(),
        "results": [],
    }
    _emit(payload, args)
    return 3 if exc.code in NEEDS_HUMAN_CODES else 1


def _log(args: argparse.Namespace, message: str) -> None:
    if not args.quiet:
        print(message, file=sys.stderr)


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            continue


if __name__ == "__main__":
    raise SystemExit(main())
