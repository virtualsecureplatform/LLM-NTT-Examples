#!/usr/bin/env python3
"""Generate one HOGE RTL bundle and run the HOGE task oracles against it."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from examples.autontt.llm_rtl_generator.behavioral_hoge import (  # noqa: E402
    HOGE_BEHAVIORAL_BUNDLE_TASKS,
    write_hoge_behavioral_bundle,
)
from examples.autontt.llm_rtl_generator.llm_client import (  # noqa: E402
    LLMClient,
    LLMClientError,
)
from examples.autontt.llm_rtl_generator.runner import (  # noqa: E402
    ChatTimeoutError,
    chat_with_timeout,
    default_sif,
    normalize_endpoint,
    parse_extra_body,
    redact_endpoint_urls,
    resolve_task,
    run_evaluator,
    write_json,
)


HOGE_BUNDLE_GENERATOR = "hoge_behavioral_bundle"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_bundle_selection_messages(tasks: list[dict[str, Any]]) -> list[dict[str, str]]:
    task_summaries = [
        {
            "id": task.get("id"),
            "name": task.get("name"),
            "top_module": task.get("top_module"),
            "mode": task.get("evaluation", {}).get("mode"),
            "candidate_file": task.get("verilog", {}).get("candidate_file"),
            "reference": task.get("reference", {}),
        }
        for task in tasks
    ]
    system = (
        "You select a bounded synthesizable RTL bundle generator for the HOGE "
        "LLM-NTT task family. Return JSON only. Do not emit Verilog, Markdown, "
        "explanations, or code fences."
    )
    user = f"""
Select the supported generator for this HOGE candidate bundle. The harness will
emit one shared candidate directory locally after validating your JSON selection,
then run each HOGE task oracle against files from that same directory.

Return exactly this JSON shape:
{{"family":"hoge","generator":"{HOGE_BUNDLE_GENERATOR}"}}

Expected selection:
```json
{json.dumps({"family": "hoge", "generator": HOGE_BUNDLE_GENERATOR}, indent=2, sort_keys=True)}
```

HOGE task boundaries that will be evaluated:
```json
{json.dumps(task_summaries, indent=2, sort_keys=True)}
```

Available bundle generators:
```json
[
  {{
    "generator": "{HOGE_BUNDLE_GENERATOR}",
    "description": "emit one HOGE candidate directory with INTTWrap, ExternalProductWrap, NTTWrap, and NTTidPackedTop RTL"
  }}
]
```
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            stripped = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response did not contain a JSON object")
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def parse_bundle_selection(text: str) -> dict[str, str]:
    parsed = extract_json_object(text)
    family = str(parsed.get("family", ""))
    generator = str(parsed.get("generator", ""))
    if family != "hoge":
        raise ValueError(f"LLM selected family {family!r}, expected 'hoge'")
    if generator != HOGE_BUNDLE_GENERATOR:
        raise ValueError(
            f"LLM selected generator {generator!r}, expected {HOGE_BUNDLE_GENERATOR!r}"
        )
    return {"family": family, "generator": generator}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate one HOGE RTL bundle and evaluate HOGE task oracles."
    )
    parser.add_argument(
        "--candidate-source",
        choices=("behavioral", "llm_behavioral"),
        default="behavioral",
        help=(
            "Use the local bounded HOGE bundle generator, or have an endpoint "
            "select that bounded generator before local RTL emission."
        ),
    )
    parser.add_argument("--endpoint", default=os.environ.get("LLM_NTT_LLM_ENDPOINT"))
    parser.add_argument("--model", default=os.environ.get("LLM_NTT_LLM_MODEL"))
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--extra-body-json")
    parser.add_argument("--output-root", default="build/hoge-bundle-runs")
    parser.add_argument(
        "--task",
        action="append",
        choices=HOGE_BEHAVIORAL_BUNDLE_TASKS,
        help="HOGE task oracle to run. May be repeated. Defaults to all HOGE bundle tasks.",
    )
    parser.add_argument("--sif", default="auto")
    parser.add_argument("--apptainer-bin", default=os.environ.get("APPTAINER_BIN", "apptainer"))
    parser.add_argument("--with-yosys", action="store_true")
    parser.add_argument("--with-vitis", action="store_true")
    parser.add_argument("--vitis-part", default=os.environ.get("VITIS_PART", "xcu280-fsvh2892-2L-e"))
    parser.add_argument("--vitis-clock-period", default=os.environ.get("VITIS_CLOCK_PERIOD", "4.0"))
    parser.add_argument("--vitis-clock-port", default=os.environ.get("VITIS_CLOCK_PORT", ""))
    parser.add_argument("--vitis-jobs", default=os.environ.get("VITIS_JOBS", "8"))
    parser.add_argument("--vitis-timeout", default=os.environ.get("VITIS_TIMEOUT", "0"))
    parser.add_argument("--vivado-bin", default=os.environ.get("VIVADO_BIN", "vivado"))
    parser.add_argument("--xilinx-settings", default=os.environ.get("XILINX_SETTINGS", ""))
    parser.add_argument("--keep-going", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    selected_task_ids = list(args.task or HOGE_BEHAVIORAL_BUNDLE_TASKS)
    task_pairs = [resolve_task(REPO_ROOT, task_id) for task_id in selected_task_ids]
    tasks = [task for _, task in task_pairs]

    sif: Path | None = None
    if args.sif.lower() != "none":
        if args.sif == "auto":
            sif = default_sif(REPO_ROOT)
        else:
            sif = Path(args.sif).expanduser().resolve()
        if sif is None:
            raise FileNotFoundError(
                "no Apptainer image found; set LLM_NTT_SIF, place llm-ntt.sif "
                "in the repo or parent directory, pass --sif FILE, or use "
                "--sif none to evaluate on the host"
            )
        if not sif.exists():
            raise FileNotFoundError(f"Apptainer image not found: {sif}")

    run_root = (REPO_ROOT / args.output_root / timestamp()).resolve()
    bundle_dir = run_root / "candidate"
    eval_root = run_root / "eval"
    run_root.mkdir(parents=True, exist_ok=True)

    selection: dict[str, str] | None = None
    if args.candidate_source == "llm_behavioral":
        endpoint = normalize_endpoint(args.endpoint)
        if not endpoint:
            raise ValueError(
                "provide --endpoint or set LLM_NTT_LLM_ENDPOINT; use --endpoint "
                "lab with LLM_NTT_LAB_ENDPOINT for a private lab endpoint"
            )
        client = LLMClient(
            endpoint=endpoint,
            model=args.model,
            api_key=os.environ.get(args.api_key_env) if args.api_key_env else None,
            timeout=args.timeout,
            extra_body=parse_extra_body(args.extra_body_json),
        )
        messages = build_bundle_selection_messages(tasks)
        write_json(run_root / "request.messages.json", messages)
        try:
            response = chat_with_timeout(
                client=client,
                messages=messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout,
            )
            write_json(run_root / "response.raw.json", response.raw)
            (run_root / "response.md").write_text(response.content, encoding="utf-8")
            selection = parse_bundle_selection(response.content)
        except (ChatTimeoutError, LLMClientError, ValueError) as exc:
            message = redact_endpoint_urls(str(exc))
            (run_root / "generation_error.txt").write_text(
                message + "\n", encoding="utf-8"
            )
            print(f"bundle generation failed: {message}")
            print(f"run directory: {run_root}")
            return 1
    else:
        selection = {"family": "hoge", "generator": HOGE_BUNDLE_GENERATOR}

    written = write_hoge_behavioral_bundle(bundle_dir)
    write_json(
        run_root / "candidate_source.json",
        {
            "source": args.candidate_source,
            "selection": selection,
            "tasks": selected_task_ids,
            "files": {name: str(path.relative_to(run_root)) for name, path in written.items()},
        },
    )

    ok = True
    summaries: list[dict[str, Any]] = []
    for task_file, task in task_pairs:
        task_id = str(task["id"])
        build_dir = eval_root / task_id
        results_file = build_dir / "results.json"
        print(f"==> {task_id}")
        status, result, stdout = run_evaluator(
            repo_root=REPO_ROOT,
            task_file=task_file,
            candidate_dir=bundle_dir,
            build_dir=build_dir,
            results_file=results_file,
            with_yosys=args.with_yosys,
            with_vitis=args.with_vitis,
            vitis_part=args.vitis_part,
            vitis_clock_period=args.vitis_clock_period,
            vitis_clock_port=args.vitis_clock_port,
            vitis_jobs=args.vitis_jobs,
            vitis_timeout=args.vitis_timeout,
            vivado_bin=args.vivado_bin,
            xilinx_settings=args.xilinx_settings,
            apptainer_bin=args.apptainer_bin,
            sif=sif,
        )
        (build_dir / "evaluator.stdout").write_text(stdout, encoding="utf-8")
        if stdout:
            print(stdout[-4000:])
        task_ok = bool(result and result.get("correct"))
        if args.with_vitis:
            task_ok = task_ok and bool(result and result.get("vitis_synthesis_passed"))
        if status != 0:
            task_ok = False
        if not task_ok:
            ok = False
        summaries.append(
            {
                "task_id": task_id,
                "status": status,
                "correct": result.get("correct") if result else None,
                "vitis_synthesis_passed": result.get("vitis_synthesis_passed") if result else None,
                "results": str(results_file.relative_to(run_root)),
            }
        )
        print(
            f"{task_id}: status={status} correct={summaries[-1]['correct']} "
            f"vitis={summaries[-1]['vitis_synthesis_passed']}"
        )
        if not task_ok and not args.keep_going:
            break

    write_json(run_root / "summary.json", {"ok": ok, "tasks": summaries})
    print(f"run directory: {run_root}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
