"""CLI runner for AutoNTT-style LLM RTL generation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .autontt_space import generate_search_points
from .llm_client import LLMClient
from .prompting import build_messages, extract_verilog, require_module


DEFAULT_ENDPOINT_ENV = "LLM_NTT_LLM_ENDPOINT"


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_task(repo_root: Path, task_arg: str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(task_arg)
    if not candidate.exists():
        candidate = repo_root / "tasks" / f"{task_arg}.json"
    if not candidate.exists():
        raise FileNotFoundError(f"task not found: {task_arg}")
    task = json.loads(candidate.read_text(encoding="utf-8"))
    return candidate.resolve(), task


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def tail_file(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def run_evaluator(
    repo_root: Path,
    task_file: Path,
    candidate_dir: Path,
    results_file: Path,
    with_yosys: bool,
) -> tuple[int, dict[str, Any] | None, str]:
    cmd = [
        str(repo_root / "scripts" / "evaluate_candidate.sh"),
        "--task",
        str(task_file),
        "--verilog-dir",
        str(candidate_dir),
        "--results",
        str(results_file),
    ]
    if with_yosys:
        cmd.append("--with-yosys")
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    parsed = None
    if results_file.exists():
        parsed = json.loads(results_file.read_text(encoding="utf-8"))
    return proc.returncode, parsed, proc.stdout


def build_feedback(
    result: dict[str, Any] | None,
    evaluator_stdout: str,
    repo_root: Path,
) -> str:
    parts: list[str] = []
    if result is not None:
        compact = {
            "correct": result.get("correct"),
            "build_passed": result.get("build_passed"),
            "test_passed": result.get("test_passed"),
            "lint_passed": result.get("lint_passed"),
            "synthesis_passed": result.get("synthesis_passed"),
            "status": result.get("status"),
            "metrics": result.get("metrics"),
        }
        parts.append("Previous result JSON summary:\n" + json.dumps(compact, indent=2))
        logs = result.get("logs", {})
        for name in ("configure", "build", "test", "lint", "yosys"):
            rel = logs.get(name)
            if not rel:
                continue
            text = tail_file(repo_root / rel)
            if text:
                parts.append(f"Tail of {name} log:\n{text}")
    if evaluator_stdout:
        parts.append("Evaluator stdout:\n" + evaluator_stdout[-4000:])
    return "\n\n".join(parts)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_extra_body(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--extra-body-json must decode to a JSON object")
    return parsed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate LLM-NTT RTL candidates from AutoNTT-style search points."
    )
    parser.add_argument("--task", default="hoge_streaming_intt_1024_p64")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get(DEFAULT_ENDPOINT_ENV),
        help=(
            "OpenAI-compatible endpoint. If omitted, the "
            f"{DEFAULT_ENDPOINT_ENV} environment variable is used."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LLM_NTT_LLM_MODEL"),
        help="Model id. If omitted, the first /models entry is used.",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable containing an optional bearer token.",
    )
    parser.add_argument("--output-root", default="build/llm-runs")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--search-index", type=int, default=0)
    parser.add_argument("--arch-type", default="IDH", help="AutoNTT arch filter, e.g. I, D, H, IDH.")
    parser.add_argument(
        "--modmul-type",
        default="AUTO",
        help="AutoNTT modmul filter: B, M, WLM, N, C, comma-separated, or AUTO.",
    )
    parser.add_argument(
        "--strategy",
        choices=("hardware", "behavioral_reference"),
        default="hardware",
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--spec-char-limit", type=int, default=36000)
    parser.add_argument("--extra-instruction", action="append", default=[])
    parser.add_argument(
        "--extra-body-json",
        help=(
            "JSON object merged into the chat request. Useful for local servers, "
            "for example '{\"chat_template_kwargs\":{\"enable_thinking\":false}}'."
        ),
    )
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Write prompts but do not call the LLM.")
    parser.add_argument("--no-evaluate", action="store_true")
    parser.add_argument("--with-yosys", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--no-test-source", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    needs_client = args.list_models or not (args.plan_only or args.dry_run)
    if needs_client and not args.endpoint:
        raise ValueError(
            f"provide --endpoint or set {DEFAULT_ENDPOINT_ENV} to an "
            "OpenAI-compatible /v1 endpoint"
        )
    repo_root = repo_root_from_here()
    task_file, task = resolve_task(repo_root, args.task)
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    client = None
    if needs_client:
        client = LLMClient(
            endpoint=args.endpoint,
            model=args.model,
            api_key=api_key,
            timeout=args.timeout,
            extra_body=parse_extra_body(args.extra_body_json),
        )

    if args.list_models:
        assert client is not None
        for model in client.list_models():
            print(model)
        return 0

    search_points = generate_search_points(
        task,
        arch_types=args.arch_type,
        modmul_types=args.modmul_type,
        strategy=args.strategy,
    )
    if args.plan_only:
        print(json.dumps(search_points, indent=2, sort_keys=True))
        return 0

    if args.attempts < 1:
        raise ValueError("--attempts must be positive")

    task_id = str(task["id"])
    run_root = (repo_root / args.output_root / task_id / timestamp()).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    write_json(run_root / "task.json", task)
    write_json(run_root / "search_points.json", search_points)

    feedback = ""
    candidate_file = str(task.get("verilog", {}).get("candidate_file", f"{task['top_module']}.v"))
    best_correct = False
    for attempt in range(args.attempts):
        point = search_points[(args.search_index + attempt) % len(search_points)]
        attempt_dir = run_root / f"attempt_{attempt:03d}_{point['name']}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        messages = build_messages(
            repo_root=repo_root,
            task_file=task_file,
            task=task,
            search_point=point,
            feedback=feedback,
            extra_instructions=args.extra_instruction,
            spec_char_limit=args.spec_char_limit,
            include_test_source=not args.no_test_source,
        )
        write_json(attempt_dir / "request.messages.json", messages)
        write_json(attempt_dir / "search_point.json", point)
        (attempt_dir / "prompt.md").write_text(messages[-1]["content"], encoding="utf-8")

        if args.dry_run:
            print(f"wrote dry-run prompt: {attempt_dir / 'prompt.md'}")
            continue

        assert client is not None
        response = client.chat(
            messages=messages,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        write_json(attempt_dir / "response.raw.json", response.raw)
        (attempt_dir / "response.md").write_text(response.content, encoding="utf-8")

        verilog = extract_verilog(response.content)
        require_module(verilog, str(task["top_module"]))
        candidate_path = attempt_dir / candidate_file
        candidate_path.write_text(verilog, encoding="utf-8")
        print(f"wrote candidate: {candidate_path}")

        if args.no_evaluate:
            continue

        results_file = attempt_dir / "results.json"
        status, result, stdout = run_evaluator(
            repo_root=repo_root,
            task_file=task_file,
            candidate_dir=attempt_dir,
            results_file=results_file,
            with_yosys=args.with_yosys,
        )
        (attempt_dir / "evaluator.stdout").write_text(stdout, encoding="utf-8")
        correct = bool(result and result.get("correct"))
        best_correct = best_correct or correct
        print(
            f"attempt {attempt}: evaluator_status={status} "
            f"correct={str(correct).lower()} results={results_file}"
        )
        if correct and not args.keep_going:
            break
        feedback = build_feedback(result, stdout, repo_root)

    print(f"run directory: {run_root}")
    if args.dry_run or args.no_evaluate:
        return 0
    return 0 if best_correct else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
