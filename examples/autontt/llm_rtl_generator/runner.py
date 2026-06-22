"""CLI runner for AutoNTT-style LLM RTL generation."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

from .autontt_space import generate_search_points
from .behavioral_hoge import (
    generate_hoge_externalproduct_behavioral,
    generate_hoge_nttid_behavioral,
    generate_hoge_streaming_intt_behavioral,
    generate_hoge_streaming_ntt_interface_behavioral,
)
from .behavioral_yata import generate_yata_raintt_behavioral
from .hardware_feedback import (
    analyze_rtl_for_hardware,
    build_hardware_feedback,
)
from .llm_client import LLMClient
from .llm_client import LLMClientError
from .prompting import build_messages, extract_verilog, validate_candidate


DEFAULT_ENDPOINT_ENV = "LLM_NTT_LLM_ENDPOINT"
DEFAULT_MODEL_ENV = "LLM_NTT_LLM_MODEL"
DEFAULT_SIF_ENV = "LLM_NTT_SIF"
LAB_ENDPOINT_ENV = "LLM_NTT_LAB_ENDPOINT"
CHISEL_REFERENCE_GENERATOR = "chisel_reference"


BEHAVIORAL_GENERATORS: dict[str, dict[str, Any]] = {
    "hoge_streaming_intt_1024_p64": {
        "name": "hoge_streaming_intt_behavioral",
        "description": "functional HOGE 1024-point streaming INTT RTL",
        "generator": generate_hoge_streaming_intt_behavioral,
    },
    "hoge_nttid_1024_identity": {
        "name": "hoge_nttid_behavioral",
        "description": "functional HOGE packed identity RTL",
        "generator": generate_hoge_nttid_behavioral,
    },
    "hoge_streaming_ntt_1024_p64": {
        "name": "hoge_streaming_ntt_interface_behavioral",
        "description": "standalone HOGE NTT wrapper interface/lint RTL",
        "generator": generate_hoge_streaming_ntt_interface_behavioral,
    },
    "hoge_externalproduct_ntt_1024_p64": {
        "name": "hoge_externalproduct_behavioral",
        "description": "functional HOGE ExternalProduct forward-NTT RTL",
        "generator": generate_hoge_externalproduct_behavioral,
    },
    "yata_raintt_512_p27": {
        "name": "yata_raintt_behavioral",
        "description": "functional YATA RAINTT INTT/NTT RTL",
        "generator": generate_yata_raintt_behavioral,
    },
}


class ChatTimeoutError(TimeoutError):
    """Raised when a chat completion exceeds the runner wall-clock limit."""


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


def normalize_endpoint(endpoint: str | None) -> str | None:
    if endpoint is None:
        return None
    endpoint = endpoint.strip()
    if not endpoint:
        return None
    if endpoint.lower() == "lab":
        endpoint = os.environ.get(LAB_ENDPOINT_ENV, "").strip()
        if not endpoint:
            raise ValueError(
                f"--endpoint lab requires {LAB_ENDPOINT_ENV} to contain the "
                "OpenAI-compatible /v1 endpoint"
            )
    if "://" not in endpoint:
        endpoint = f"http://{endpoint}"
    parsed = urlparse(endpoint)
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def default_sif(repo_root: Path) -> Path | None:
    env_value = os.environ.get(DEFAULT_SIF_ENV)
    candidates = []
    if env_value:
        candidates.append(Path(env_value))
    candidates.extend([repo_root / "llm-ntt.sif", repo_root.parent / "llm-ntt.sif"])
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return candidate.resolve()
    return None


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
    build_dir: Path,
    results_file: Path,
    with_yosys: bool,
    with_vitis: bool,
    vitis_part: str,
    vitis_clock_period: str,
    vitis_clock_port: str,
    vitis_jobs: str,
    vitis_timeout: str = "0",
    vivado_bin: str = "vivado",
    xilinx_settings: str = "",
    apptainer_bin: str | None = None,
    sif: Path | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    if with_vitis and sif is not None:
        cmd = [
            str(repo_root / "scripts" / "evaluate_with_apptainer_and_vitis.sh"),
            "--sif",
            str(sif),
            "--apptainer-bin",
            apptainer_bin or "apptainer",
        ]
    else:
        cmd = [str(repo_root / "scripts" / "evaluate_candidate.sh")]

    cmd.extend(
        [
        "--task",
        str(task_file),
        "--verilog-dir",
        str(candidate_dir),
        "--build-dir",
        str(build_dir),
        "--results",
        str(results_file),
        ]
    )
    if with_yosys:
        cmd.append("--with-yosys")
    if with_vitis:
        if sif is None:
            cmd.append("--with-vitis")
        cmd.extend(["--vitis-part", vitis_part])
        cmd.extend(
            [
                "--vitis-clock-period",
                vitis_clock_period,
                "--vitis-jobs",
                vitis_jobs,
                "--vitis-timeout",
                vitis_timeout,
                "--vivado-bin",
                vivado_bin,
            ]
        )
        if vitis_clock_port:
            cmd.extend(["--vitis-clock-port", vitis_clock_port])
        if xilinx_settings:
            cmd.extend(["--xilinx-settings", xilinx_settings])

    if sif is not None and not with_vitis:
        cmd = [
            apptainer_bin or "apptainer",
            "exec",
            "--no-home",
            "--pwd",
            str(repo_root),
            "--bind",
            f"{repo_root}:{repo_root}",
            str(sif),
            *cmd,
        ]
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
        for name in ("configure", "build", "test", "lint", "yosys", "vitis"):
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


def redact_endpoint_urls(text: str) -> str:
    return re.sub(r"https?://[^\s/]+(?:/[^\s]*)?", "<endpoint>", text)


def behavioral_generator_entry(task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("id", ""))
    entry = BEHAVIORAL_GENERATORS.get(task_id)
    if entry is None:
        supported = ", ".join(sorted(BEHAVIORAL_GENERATORS))
        raise ValueError(
            "behavioral generation currently supports only "
            f"{supported}"
        )
    return entry


def behavioral_generator_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for task_id, entry in sorted(BEHAVIORAL_GENERATORS.items()):
        options.append(
            {
                "task_id": task_id,
                "generator": str(entry["name"]),
                "description": str(entry["description"]),
            }
        )
    return options


def build_generator_selection_messages(
    task_file: Path,
    task: dict[str, Any],
    search_point: dict[str, Any],
    feedback: str = "",
) -> list[dict[str, str]]:
    expected = behavioral_generator_entry(task)
    expected_payload = {
        "task_id": str(task["id"]),
        "generator": str(expected["name"]),
    }
    system = (
        "You select a bounded functional RTL generator for an LLM-NTT task. "
        "Return JSON only. Do not emit Verilog, Markdown, explanations, or "
        "code fences."
    )
    user = f"""
Select the supported generator that should be used for this task. The harness
will emit the RTL locally after validating your JSON selection.

Return exactly this JSON shape:
{{"task_id":"<task id>","generator":"<generator name>"}}

Expected task:
```json
{json.dumps(expected_payload, indent=2, sort_keys=True)}
```

Task manifest path:
{task_file}

Task summary:
```json
{json.dumps({
    "id": task.get("id"),
    "name": task.get("name"),
    "top_module": task.get("top_module"),
    "variant": task.get("variant"),
    "parameters": task.get("parameters", {}),
    "evaluation": task.get("evaluation", {}),
}, indent=2, sort_keys=True)}
```

Selected AutoNTT-style search point:
```json
{json.dumps(search_point, indent=2, sort_keys=True)}
```

Available generators:
```json
{json.dumps(behavioral_generator_options(), indent=2, sort_keys=True)}
```

Previous attempt feedback:
```text
{feedback or "No previous attempt."}
```
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_chisel_generator_selection_messages(
    task_file: Path,
    task: dict[str, Any],
    search_point: dict[str, Any],
    feedback: str = "",
) -> list[dict[str, str]]:
    expected_payload = {
        "task_id": str(task["id"]),
        "generator": CHISEL_REFERENCE_GENERATOR,
    }
    system = (
        "You select a bounded synthesizable RTL generator for an LLM-NTT task. "
        "Return JSON only. Do not emit Verilog, Markdown, explanations, or "
        "code fences."
    )
    user = f"""
Select the supported synthesizable generator that should be used for this task.
The harness will run the generator locally after validating your JSON selection.

Return exactly this JSON shape:
{{"task_id":"<task id>","generator":"{CHISEL_REFERENCE_GENERATOR}"}}

Expected selection:
```json
{json.dumps(expected_payload, indent=2, sort_keys=True)}
```

Task manifest path:
{task_file}

Task summary:
```json
{json.dumps({
    "id": task.get("id"),
    "name": task.get("name"),
    "top_module": task.get("top_module"),
    "variant": task.get("variant"),
    "parameters": task.get("parameters", {}),
    "evaluation": task.get("evaluation", {}),
}, indent=2, sort_keys=True)}
```

Selected AutoNTT-style search point:
```json
{json.dumps(search_point, indent=2, sort_keys=True)}
```

Available synthesizable generators:
```json
{json.dumps([{
    "generator": CHISEL_REFERENCE_GENERATOR,
    "description": "regenerate the task's checked-in Chisel RTL in a temporary build directory",
}], indent=2, sort_keys=True)}
```

Previous attempt feedback:
```text
{feedback or "No previous attempt."}
```
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        fence = stripped.splitlines()
        if len(fence) >= 3 and fence[0].startswith("```") and fence[-1].startswith("```"):
            stripped = "\n".join(fence[1:-1]).strip()
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


def parse_behavioral_generator_selection(
    response_text: str,
    task: dict[str, Any],
) -> dict[str, str]:
    parsed = _extract_json_object(response_text)
    expected = behavioral_generator_entry(task)
    expected_task_id = str(task.get("id", ""))
    expected_generator = str(expected["name"])
    selected_task_id = str(parsed.get("task_id", ""))
    selected_generator = str(parsed.get("generator", ""))
    if selected_task_id != expected_task_id:
        raise ValueError(
            "LLM selected task_id "
            f"{selected_task_id!r}, expected {expected_task_id!r}"
        )
    if selected_generator != expected_generator:
        raise ValueError(
            "LLM selected generator "
            f"{selected_generator!r}, expected {expected_generator!r}"
        )
    return {
        "task_id": selected_task_id,
        "generator": selected_generator,
    }


def parse_chisel_generator_selection(
    response_text: str,
    task: dict[str, Any],
) -> dict[str, str]:
    parsed = _extract_json_object(response_text)
    expected_task_id = str(task.get("id", ""))
    selected_task_id = str(parsed.get("task_id", ""))
    selected_generator = str(parsed.get("generator", ""))
    if selected_task_id != expected_task_id:
        raise ValueError(
            "LLM selected task_id "
            f"{selected_task_id!r}, expected {expected_task_id!r}"
        )
    if selected_generator != CHISEL_REFERENCE_GENERATOR:
        raise ValueError(
            "LLM selected generator "
            f"{selected_generator!r}, expected {CHISEL_REFERENCE_GENERATOR!r}"
        )
    return {
        "task_id": selected_task_id,
        "generator": selected_generator,
    }


def copy_reference_candidate(
    repo_root: Path,
    task: dict[str, Any],
    attempt_dir: Path,
    candidate_file: str,
) -> Path:
    default_path = str(task.get("verilog", {}).get("default_path", ""))
    if not default_path:
        raise ValueError("task manifest does not define verilog.default_path")
    source_path = repo_root / default_path
    if not source_path.exists():
        raise FileNotFoundError(f"reference RTL not found: {source_path}")
    candidate_path = attempt_dir / candidate_file
    shutil.copyfile(source_path, candidate_path)
    return candidate_path


def _copy_chisel_project(source_path: Path, work_path: Path) -> None:
    ignore = shutil.ignore_patterns(
        "target",
        ".bsp",
        ".metals",
        "*.anno.json",
        "*.fir",
        "*.v",
    )
    shutil.copytree(source_path, work_path, ignore=ignore)


def write_chisel_reference_candidate(
    repo_root: Path,
    task: dict[str, Any],
    attempt_dir: Path,
    candidate_file: str,
    sbt_bin: str = "sbt",
    apptainer_bin: str | None = None,
    sif: Path | None = None,
    timeout_seconds: int = 900,
) -> Path:
    variant = str(task.get("variant", "")).strip()
    if not variant:
        raise ValueError("task manifest does not define variant for Chisel generation")
    source_path = repo_root / "variants" / variant / "chisel"
    if not source_path.exists():
        raise FileNotFoundError(f"Chisel project not found: {source_path}")

    task_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(task.get("id", "task")))
    tmp_root = Path(
        tempfile.mkdtemp(
            prefix=f"llm-ntt-chisel-{task_id}-",
            dir=os.environ.get("TMPDIR", "/tmp"),
        )
    )
    work_path = tmp_root / "chisel"
    _copy_chisel_project(source_path, work_path)
    tmp_home = tmp_root / "home"
    tmp_home.mkdir()

    if shutil.which(sbt_bin):
        cmd = [sbt_bin, "run"]
    elif sif is not None:
        cmd = [
            apptainer_bin or "apptainer",
            "exec",
            "--home",
            str(tmp_home),
            "--pwd",
            str(work_path),
            "--bind",
            f"{tmp_root}:{tmp_root}",
            str(sif),
            sbt_bin,
            "run",
        ]
    else:
        raise FileNotFoundError(
            f"{sbt_bin!r} was not found on PATH and no Apptainer image is available"
        )

    log_path = attempt_dir / "chisel_generate.log"
    metadata = {
        "source": "chisel_reference",
        "variant": variant,
        "source_project": str(source_path),
        "work_dir": str(work_path),
        "home_dir": str(tmp_home),
        "sbt_bin": sbt_bin,
        "command": cmd,
        "timeout_seconds": timeout_seconds,
        "log": str(log_path),
    }
    try:
        proc = subprocess.run(
            cmd,
            cwd=work_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        log_path.write_text(
            partial
            + f"\nChisel generation timed out after {timeout_seconds} seconds.\n",
            encoding="utf-8",
        )
        metadata["returncode"] = "timeout"
        write_json(attempt_dir / "chisel_generate.json", metadata)
        raise TimeoutError(
            f"Chisel generation timed out after {timeout_seconds} seconds; see {log_path}"
        ) from exc

    log_path.write_text(proc.stdout, encoding="utf-8")
    metadata["returncode"] = proc.returncode
    write_json(attempt_dir / "chisel_generate.json", metadata)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Chisel generation failed with status {proc.returncode}; see {log_path}"
        )

    generated_path = work_path / candidate_file
    if not generated_path.exists():
        top_candidate = work_path / f"{task['top_module']}.v"
        if top_candidate.exists():
            generated_path = top_candidate
        else:
            raise FileNotFoundError(
                f"Chisel generation did not produce {candidate_file} or "
                f"{top_candidate.name}; see {log_path}"
            )
    candidate_path = attempt_dir / candidate_file
    shutil.copyfile(generated_path, candidate_path)
    return candidate_path


def write_behavioral_candidate(
    task: dict[str, Any],
    attempt_dir: Path,
    candidate_file: str,
) -> Path:
    entry = behavioral_generator_entry(task)
    generator: Callable[[], str] = entry["generator"]
    candidate_path = attempt_dir / candidate_file
    candidate_path.write_text(
        generator(),
        encoding="utf-8",
    )
    return candidate_path


def behavioral_generator_name(task: dict[str, Any]) -> str:
    return str(behavioral_generator_entry(task)["name"])


def _raise_chat_timeout(signum: int, frame: Any) -> None:
    raise ChatTimeoutError("chat completion exceeded wall-clock timeout")


def chat_with_timeout(
    client: LLMClient,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
) -> Any:
    if timeout_seconds <= 0:
        return client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_chat_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate LLM-NTT RTL candidates from AutoNTT-style search points."
    )
    parser.add_argument("--task", default="hoge_streaming_intt_1024_p64")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get(DEFAULT_ENDPOINT_ENV),
        help=(
            "OpenAI-compatible endpoint. Use 'lab' to read the endpoint from "
            f"{LAB_ENDPOINT_ENV}. If omitted, {DEFAULT_ENDPOINT_ENV} is used."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(DEFAULT_MODEL_ENV),
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
    parser.add_argument(
        "--goal",
        choices=("correctness", "hardware"),
        default="correctness",
        help=(
            "Generation success criterion. 'correctness' stops after the "
            "task evaluator passes. 'hardware' requires a hardware-shaped RTL "
            "screen plus Vivado/Vitis synthesis metrics."
        ),
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
    parser.add_argument(
        "--candidate-source",
        choices=(
            "llm",
            "reference",
            "behavioral",
            "llm_behavioral",
            "chisel_reference",
            "llm_chisel_reference",
        ),
        default="llm",
        help=(
            "Use the LLM response as the candidate, or copy the task's golden "
            "RTL into the AutoNTT-style run directory, or emit a built-in "
            "behavioral functional RTL generator for supported tasks. "
            "llm_behavioral asks the LLM to select a supported bounded "
            "functional generator, then emits that RTL locally. "
            "chisel_reference regenerates the checked-in Chisel top in /tmp; "
            "llm_chisel_reference has the endpoint select that bounded "
            "synthesizable generator before running it locally."
        ),
    )
    parser.add_argument(
        "--sbt-bin",
        default=os.environ.get("SBT_BIN", "sbt"),
        help="sbt executable used by --candidate-source chisel_reference.",
    )
    parser.add_argument(
        "--chisel-timeout",
        type=int,
        default=int(os.environ.get("CHISEL_TIMEOUT", "900")),
        help=(
            "Timeout in seconds for Chisel/SBT candidate generation. Use 0 "
            "to disable the timeout."
        ),
    )
    parser.add_argument(
        "--allow-shortcuts",
        action="store_true",
        help=(
            "Allow trivial pass-through candidates. This is intended only for "
            "explicit smoke/debug runs; real arithmetic tasks reject shortcuts "
            "by default."
        ),
    )
    parser.add_argument(
        "--sif",
        default="auto",
        help=(
            "Apptainer image for evaluation. Defaults to auto-detecting "
            f"{DEFAULT_SIF_ENV}, ./llm-ntt.sif, or ../llm-ntt.sif. Use 'none' "
            "to evaluate on the host."
        ),
    )
    parser.add_argument(
        "--apptainer-bin",
        default=os.environ.get("APPTAINER_BIN", "apptainer"),
        help="Apptainer executable used when --sif is not 'none'.",
    )
    parser.add_argument("--with-yosys", action="store_true")
    parser.add_argument(
        "--no-yosys",
        action="store_true",
        help=(
            "Do not auto-run Yosys for --goal hardware. The hardware goal "
            "still requires Vivado/Vitis synthesis metrics."
        ),
    )
    parser.add_argument(
        "--with-vitis",
        action="store_true",
        help=(
            "Run optional Vivado/Vitis RTL synthesis after functional "
            "evaluation. With Apptainer evaluation, synthesis is run on the "
            "host via scripts/evaluate_with_apptainer_and_vitis.sh."
        ),
    )
    parser.add_argument(
        "--vitis-part",
        default=os.environ.get("VITIS_PART", "xcu280-fsvh2892-2L-e"),
        help="FPGA part for --with-vitis.",
    )
    parser.add_argument(
        "--vitis-clock-period",
        default=os.environ.get("VITIS_CLOCK_PERIOD", "4.0"),
        help="Clock period in ns for --with-vitis.",
    )
    parser.add_argument(
        "--vitis-clock-port",
        default=os.environ.get("VITIS_CLOCK_PORT", ""),
        help="Clock port for --with-vitis. Defaults to the task manifest.",
    )
    parser.add_argument(
        "--vitis-jobs",
        default=os.environ.get("VITIS_JOBS", "8"),
        help="Vivado worker thread hint for --with-vitis.",
    )
    parser.add_argument(
        "--vitis-timeout",
        default=os.environ.get("VITIS_TIMEOUT", ""),
        help=(
            "Optional timeout in seconds for each Vivado/Vitis synthesis run. "
            "Hardware goal defaults to 3600 when this is omitted."
        ),
    )
    parser.add_argument(
        "--vivado-bin",
        default=os.environ.get("VIVADO_BIN", "vivado"),
        help="Vivado executable for --with-vitis.",
    )
    parser.add_argument(
        "--xilinx-settings",
        default=os.environ.get("XILINX_SETTINGS", ""),
        help=(
            "Xilinx settings script for --with-vitis. Defaults inside the "
            "synthesis helper when omitted."
        ),
    )
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--no-test-source", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.no_yosys:
        args.with_yosys = False
    if args.goal == "hardware":
        if not args.no_yosys:
            args.with_yosys = True
        args.with_vitis = True
        if not args.vitis_timeout:
            args.vitis_timeout = "3600"
    elif not args.vitis_timeout:
        args.vitis_timeout = "0"
    needs_client = args.list_models or (
        args.candidate_source in ("llm", "llm_behavioral", "llm_chisel_reference")
        and not (args.plan_only or args.dry_run)
    )
    if needs_client:
        args.endpoint = normalize_endpoint(args.endpoint)
    if needs_client and not args.endpoint:
        raise ValueError(
            f"provide --endpoint or set {DEFAULT_ENDPOINT_ENV} to an "
            "OpenAI-compatible /v1 endpoint; use --endpoint lab with "
            f"{LAB_ENDPOINT_ENV} for a private lab endpoint"
        )
    repo_root = repo_root_from_here()
    task_file, task = resolve_task(repo_root, args.task)
    sif: Path | None = None
    if args.sif.lower() != "none":
        if args.sif == "auto":
            sif = default_sif(repo_root)
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
    best_success = False
    valid_candidate = False
    for attempt in range(args.attempts):
        point = search_points[(args.search_index + attempt) % len(search_points)]
        attempt_dir = run_root / f"attempt_{attempt:03d}_{point['name']}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        if args.candidate_source == "llm_behavioral":
            messages = build_generator_selection_messages(
                task_file=task_file,
                task=task,
                search_point=point,
                feedback=feedback,
            )
        elif args.candidate_source == "llm_chisel_reference":
            messages = build_chisel_generator_selection_messages(
                task_file=task_file,
                task=task,
                search_point=point,
                feedback=feedback,
            )
        else:
            extra_instructions = list(args.extra_instruction)
            if args.goal == "hardware":
                extra_instructions.extend(
                    [
                        "Hardware goal is enabled: success requires "
                        "Vivado/Vitis out-of-context synthesis on the target "
                        "part, not only Verilator correctness.",
                        "Do not compute a full NTT/INTT/ExternalProduct in one "
                        "procedural task, function, or clock edge. Use an FSM "
                        "over stages/blocks with the selected iterative, "
                        "dataflow, or hybrid architecture.",
                        "Respect the selected butterfly_budget as an upper "
                        "bound for concurrent butterfly/modular-multiply "
                        "datapaths; reuse or pipeline arithmetic instead of "
                        "instantiating one multiplier per coefficient.",
                        "Use explicit coefficient and twiddle storage with "
                        "bounded read/write ports. Prefer pipelined Barrett, "
                        "Montgomery, or prime-specific reduction; avoid % and "
                        "/ operators for large modular arithmetic.",
                    ]
                )
            messages = build_messages(
                repo_root=repo_root,
                task_file=task_file,
                task=task,
                search_point=point,
                feedback=feedback,
                extra_instructions=extra_instructions,
                spec_char_limit=args.spec_char_limit,
                include_test_source=not args.no_test_source,
            )
        write_json(attempt_dir / "request.messages.json", messages)
        write_json(attempt_dir / "search_point.json", point)
        (attempt_dir / "prompt.md").write_text(messages[-1]["content"], encoding="utf-8")

        if args.dry_run:
            print(f"wrote dry-run prompt: {attempt_dir / 'prompt.md'}")
            continue

        if args.candidate_source == "reference":
            candidate_path = copy_reference_candidate(
                repo_root=repo_root,
                task=task,
                attempt_dir=attempt_dir,
                candidate_file=candidate_file,
            )
            write_json(
                attempt_dir / "candidate_source.json",
                {
                    "source": "reference",
                    "reference_path": str(
                        repo_root / str(task["verilog"]["default_path"])
                    ),
                    "search_point": point["name"],
                },
            )
            verilog = candidate_path.read_text(encoding="utf-8", errors="replace")
        elif args.candidate_source == "behavioral":
            candidate_path = write_behavioral_candidate(
                task=task,
                attempt_dir=attempt_dir,
                candidate_file=candidate_file,
            )
            write_json(
                attempt_dir / "candidate_source.json",
                {
                    "source": "behavioral",
                    "generator": behavioral_generator_name(task),
                    "search_point": point["name"],
                },
            )
            verilog = candidate_path.read_text(encoding="utf-8", errors="replace")
        elif args.candidate_source == "chisel_reference":
            try:
                candidate_path = write_chisel_reference_candidate(
                    repo_root=repo_root,
                    task=task,
                    attempt_dir=attempt_dir,
                    candidate_file=candidate_file,
                    sbt_bin=args.sbt_bin,
                    apptainer_bin=args.apptainer_bin,
                    sif=sif,
                    timeout_seconds=args.chisel_timeout,
                )
            except (RuntimeError, FileNotFoundError, TimeoutError, ValueError) as exc:
                message = str(exc)
                (attempt_dir / "generation_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: Chisel generation failed: {message}")
                feedback = (
                    "Chisel reference generation failed before RTL emission:\n"
                    f"{message}\n\n"
                    "The next attempt should use a supported task with a "
                    "checked-in Chisel project."
                )
                continue
            write_json(
                attempt_dir / "candidate_source.json",
                {
                    "source": "chisel_reference",
                    "generator": CHISEL_REFERENCE_GENERATOR,
                    "search_point": point["name"],
                },
            )
            verilog = candidate_path.read_text(encoding="utf-8", errors="replace")
        elif args.candidate_source == "llm_behavioral":
            assert client is not None
            try:
                response = chat_with_timeout(
                    client=client,
                    messages=messages,
                    temperature=args.temperature,
                    max_tokens=min(args.max_tokens, 2048),
                    timeout_seconds=args.timeout,
                )
            except ChatTimeoutError as exc:
                message = f"{exc} after {args.timeout}s"
                (attempt_dir / "llm_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: LLM request timed out: {message}")
                feedback = (
                    "The previous generator-selection request timed out. "
                    "Return only the expected small JSON object."
                )
                continue
            except LLMClientError as exc:
                message = redact_endpoint_urls(str(exc))
                (attempt_dir / "llm_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: LLM request failed: {message}")
                feedback = (
                    "The previous generator-selection request failed before "
                    f"the endpoint returned JSON:\n{message}\n\n"
                    "Return only the expected small JSON object when the "
                    "endpoint is available."
                )
                continue
            write_json(attempt_dir / "response.raw.json", response.raw)
            (attempt_dir / "response.md").write_text(
                response.content, encoding="utf-8"
            )
            try:
                selection = parse_behavioral_generator_selection(
                    response.content,
                    task,
                )
            except ValueError as exc:
                message = str(exc)
                (attempt_dir / "validation_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: validation failed: {message}")
                feedback = (
                    "Generator selection failed before RTL emission:\n"
                    f"{message}\n\n"
                    "Return only the exact JSON object requested by the prompt."
                )
                continue
            candidate_path = write_behavioral_candidate(
                task=task,
                attempt_dir=attempt_dir,
                candidate_file=candidate_file,
            )
            write_json(
                attempt_dir / "candidate_source.json",
                {
                    "source": "llm_behavioral",
                    "generator": selection["generator"],
                    "llm_selection": selection,
                    "search_point": point["name"],
                },
            )
            verilog = candidate_path.read_text(encoding="utf-8", errors="replace")
        elif args.candidate_source == "llm_chisel_reference":
            assert client is not None
            try:
                response = chat_with_timeout(
                    client=client,
                    messages=messages,
                    temperature=args.temperature,
                    max_tokens=min(args.max_tokens, 2048),
                    timeout_seconds=args.timeout,
                )
            except ChatTimeoutError as exc:
                message = f"{exc} after {args.timeout}s"
                (attempt_dir / "llm_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: LLM request timed out: {message}")
                feedback = (
                    "The previous synthesizable generator-selection request "
                    "timed out. Return only the expected small JSON object."
                )
                continue
            except LLMClientError as exc:
                message = redact_endpoint_urls(str(exc))
                (attempt_dir / "llm_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: LLM request failed: {message}")
                feedback = (
                    "The previous synthesizable generator-selection request "
                    f"failed before the endpoint returned JSON:\n{message}\n\n"
                    "Return only the expected small JSON object when the "
                    "endpoint is available."
                )
                continue
            write_json(attempt_dir / "response.raw.json", response.raw)
            (attempt_dir / "response.md").write_text(
                response.content, encoding="utf-8"
            )
            try:
                selection = parse_chisel_generator_selection(response.content, task)
                candidate_path = write_chisel_reference_candidate(
                    repo_root=repo_root,
                    task=task,
                    attempt_dir=attempt_dir,
                    candidate_file=candidate_file,
                    sbt_bin=args.sbt_bin,
                    apptainer_bin=args.apptainer_bin,
                    sif=sif,
                    timeout_seconds=args.chisel_timeout,
                )
            except (RuntimeError, FileNotFoundError, TimeoutError, ValueError) as exc:
                message = str(exc)
                (attempt_dir / "validation_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: validation failed: {message}")
                feedback = (
                    "Synthesizable generator selection or execution failed:\n"
                    f"{message}\n\n"
                    "Return only the exact JSON object requested by the prompt."
                )
                continue
            write_json(
                attempt_dir / "candidate_source.json",
                {
                    "source": "llm_chisel_reference",
                    "generator": selection["generator"],
                    "llm_selection": selection,
                    "search_point": point["name"],
                },
            )
            verilog = candidate_path.read_text(encoding="utf-8", errors="replace")
        else:
            assert client is not None
            try:
                response = chat_with_timeout(
                    client=client,
                    messages=messages,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    timeout_seconds=args.timeout,
                )
            except ChatTimeoutError as exc:
                message = f"{exc} after {args.timeout}s"
                (attempt_dir / "llm_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: LLM request timed out: {message}")
                feedback = (
                    "The previous chat completion timed out before producing RTL. "
                    "Respond with a shorter complete implementation and avoid "
                    "extended explanation."
                )
                continue
            except LLMClientError as exc:
                message = redact_endpoint_urls(str(exc))
                (attempt_dir / "llm_error.txt").write_text(
                    message + "\n", encoding="utf-8"
                )
                print(f"attempt {attempt}: LLM request failed: {message}")
                feedback = (
                    "The previous chat completion request failed before RTL "
                    f"was produced:\n{message}\n\n"
                    "When the endpoint is available, respond with one complete "
                    "synthesizable Verilog implementation."
                )
                continue
            write_json(attempt_dir / "response.raw.json", response.raw)
            (attempt_dir / "response.md").write_text(
                response.content, encoding="utf-8"
            )

            verilog = extract_verilog(response.content)
            candidate_path = attempt_dir / candidate_file
            candidate_path.write_text(verilog, encoding="utf-8")
        print(f"wrote candidate: {candidate_path}")
        try:
            validate_candidate(verilog, task, allow_shortcuts=args.allow_shortcuts)
        except ValueError as exc:
            message = str(exc)
            (attempt_dir / "validation_error.txt").write_text(
                message + "\n", encoding="utf-8"
            )
            print(f"attempt {attempt}: validation failed: {message}")
            feedback = (
                "Candidate validation failed before evaluator execution:\n"
                f"{message}\n\n"
                "Return a complete synthesizable replacement for the whole "
                "module, with no placeholders or shortcuts."
            )
            continue
        valid_candidate = True

        hardware_analysis = None
        if args.goal == "hardware":
            hardware_analysis = analyze_rtl_for_hardware(
                verilog=verilog,
                task=task,
                search_point=point,
            )
            write_json(attempt_dir / "hardware_screen.json", hardware_analysis)
            if not hardware_analysis.get("passed", False):
                print(
                    f"attempt {attempt}: hardware screen failed "
                    f"results={attempt_dir / 'hardware_screen.json'}"
                )
                feedback = build_hardware_feedback(
                    analysis=hardware_analysis,
                    result=None,
                    repo_root=repo_root,
                )
                continue

        if args.no_evaluate:
            continue

        build_dir = attempt_dir / "eval-build"
        results_file = attempt_dir / "results.json"
        status, result, stdout = run_evaluator(
            repo_root=repo_root,
            task_file=task_file,
            candidate_dir=attempt_dir,
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
        (attempt_dir / "evaluator.stdout").write_text(stdout, encoding="utf-8")
        correct = bool(result and result.get("correct"))
        hardware_ok = bool(
            result
            and correct
            and result.get("vitis_synthesis_passed")
            and result.get("metrics", {}).get("vitis_lut") is not None
        )
        attempt_success = hardware_ok if args.goal == "hardware" else correct
        best_correct = best_correct or correct
        best_success = best_success or attempt_success
        print(
            f"attempt {attempt}: evaluator_status={status} "
            f"correct={str(correct).lower()} "
            f"hardware={str(hardware_ok).lower()} results={results_file}"
        )
        if attempt_success and not args.keep_going:
            break
        feedback = build_feedback(result, stdout, repo_root)
        if args.goal == "hardware" and not hardware_ok:
            hardware_feedback = build_hardware_feedback(
                analysis=hardware_analysis,
                result=result,
                repo_root=repo_root,
            )
            if hardware_feedback:
                feedback = "\n\n".join(part for part in (feedback, hardware_feedback) if part)

    print(f"run directory: {run_root}")
    if args.dry_run:
        return 0
    if args.no_evaluate:
        return 0 if valid_candidate else 1
    return 0 if best_success else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
