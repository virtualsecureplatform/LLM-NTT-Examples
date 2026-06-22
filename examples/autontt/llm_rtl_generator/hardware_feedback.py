"""Hardware-oriented RTL screening and synthesis feedback helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)
_FOR_RE = re.compile(
    r"\bfor\s*\([^;]*?;\s*[^;]*?(?:<|<=)\s*([^;)\n]+)\s*;",
    re.IGNORECASE,
)
_TRANSFORM_TASK_RE = re.compile(
    r"\btask(?:\s+automatic)?\s+\w*(?:compute|transform|ntt|intt|externalproduct)\w*",
    re.IGNORECASE,
)


def _strip_comments(verilog: str) -> str:
    return _COMMENT_RE.sub("", verilog)


def _int_param(task: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(task.get("parameters", {}).get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _simple_bound_value(bound: str, task: dict[str, Any]) -> int | None:
    bound = bound.strip()
    bound = re.sub(r"\[[^\]]+\]", "", bound)
    params = task.get("parameters", {})
    symbols = {
        "N": _int_param(task, "N"),
        "POLY_SIZE": _int_param(task, "N"),
        "LANES": _int_param(task, "lanes"),
        "RADIX": _int_param(task, "radix"),
    }
    for key, value in params.items():
        if isinstance(value, int):
            symbols[str(key)] = value
            symbols[str(key).upper()] = value
    if re.fullmatch(r"\d+", bound):
        return int(bound)
    if re.fullmatch(r"\d+'[sS]?[dD][0-9_]+", bound):
        return int(bound.split("d", 1)[1].replace("_", ""))
    if re.fullmatch(r"\d+'[sS]?[hH][0-9a-fA-F_]+", bound):
        return int(bound.split("h", 1)[1].replace("_", ""), 16)
    if bound in symbols:
        return int(symbols[bound])
    match = re.fullmatch(r"([A-Za-z_]\w*)\s*/\s*(\d+)", bound)
    if match and match.group(1) in symbols:
        return int(symbols[match.group(1)]) // int(match.group(2))
    match = re.fullmatch(r"([A-Za-z_]\w*)\s*>>\s*(\d+)", bound)
    if match and match.group(1) in symbols:
        return int(symbols[match.group(1)]) >> int(match.group(2))
    return None


def _allows_behavioral_shortcut(task: dict[str, Any]) -> bool:
    task_id = str(task.get("id", "")).lower()
    if "identity" in task_id:
        return True
    if str(task.get("evaluation", {}).get("mode", "")) == "lint_only":
        return True
    operation = str(task.get("reference", {}).get("operation", "")).lower()
    return "identity" in operation


def analyze_rtl_for_hardware(
    verilog: str,
    task: dict[str, Any],
    search_point: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a conservative pre-synthesis hardware screen.

    This is not a proof of synthesizability. It catches common behavioral
    shortcuts before they consume long Vivado runs; Vivado/Vitis remains the
    authoritative hardware gate.
    """

    stripped = _strip_comments(verilog)
    lowered = stripped.lower()
    problem_size = _int_param(task, "N")
    lanes = _int_param(task, "lanes", default=max(1, problem_size))
    budget = 0
    if search_point is not None:
        try:
            budget = int(search_point.get("butterfly_budget", 0) or 0)
        except (TypeError, ValueError):
            budget = 0

    loop_bounds: list[int] = []
    unknown_loop_bounds = 0
    for match in _FOR_RE.finditer(stripped):
        value = _simple_bound_value(match.group(1), task)
        if value is None:
            unknown_loop_bounds += 1
        else:
            loop_bounds.append(value)

    large_loop_threshold = max(128, problem_size // 2 if problem_size else 128)
    large_loops = [value for value in loop_bounds if value >= large_loop_threshold]
    transform_task_count = len(_TRANSFORM_TASK_RE.findall(stripped))
    always_count = len(re.findall(r"\balways\b", lowered))
    task_count = len(re.findall(r"\btask\b", lowered))
    function_count = len(re.findall(r"\bfunction\b", lowered))
    multiply_tokens = stripped.count("*")
    division_tokens = len(re.findall(r"(?<!/)/(?!/)", stripped))
    modulo_tokens = stripped.count("%")

    issues: list[str] = []
    warnings: list[str] = []
    if not _allows_behavioral_shortcut(task):
        if transform_task_count and large_loops:
            issues.append(
                "RTL appears to implement a full-polynomial transform in "
                "procedural task/function loops; use an FSM with bounded "
                "butterfly units instead of computing all coefficients in one "
                "activation."
            )
        if always_count <= 1 and transform_task_count and problem_size >= 512:
            issues.append(
                "RTL has one or fewer always blocks plus transform tasks for a "
                "large arithmetic task; this is usually a simulation model, "
                "not a staged datapath."
            )
        if modulo_tokens:
            warnings.append(
                "RTL uses the % operator; Vivado may infer expensive division "
                "logic unless this is constrained to a small constant reducer."
            )
        if division_tokens:
            warnings.append(
                "RTL uses the / operator; prefer explicit Barrett, Montgomery, "
                "or prime-specific reduction hardware."
            )
        if budget and multiply_tokens > max(32, budget * 8):
            warnings.append(
                "Source contains many multiplication operators relative to the "
                "selected butterfly budget; check that multipliers are reused "
                "or pipelined."
            )

    return {
        "passed": not issues,
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "always_count": always_count,
            "task_count": task_count,
            "function_count": function_count,
            "for_loop_count": len(loop_bounds) + unknown_loop_bounds,
            "large_for_loop_count": len(large_loops),
            "max_for_loop_bound": max(loop_bounds) if loop_bounds else None,
            "unknown_for_loop_bounds": unknown_loop_bounds,
            "transform_task_count": transform_task_count,
            "multiply_token_count": multiply_tokens,
            "division_token_count": division_tokens,
            "modulo_token_count": modulo_tokens,
            "problem_size": problem_size,
            "lanes": lanes,
            "butterfly_budget": budget,
        },
    }


def summarize_vitis_log(log_text: str) -> dict[str, Any]:
    rejected = [int(value) for value in re.findall(r"Rejected \((\d+) > 9024\)", log_text)]
    accepted = [int(value) for value in re.findall(r"Accepted \((\d+) < 9024\)", log_text)]
    return {
        "dsp_rejected_count": len(rejected),
        "dsp_accepted_count": len(accepted),
        "max_rejected_dsp_count": max(rejected) if rejected else None,
        "min_rejected_dsp_count": min(rejected) if rejected else None,
        "max_accepted_dsp_count": max(accepted) if accepted else None,
        "timing_optimization_started": "Start Timing Optimization" in log_text,
        "synth_design_completed": "synth_design completed successfully" in log_text,
        "vivado_errors": len(re.findall(r"\bERROR:", log_text)),
        "vivado_critical_warnings": len(re.findall(r"CRITICAL WARNING", log_text)),
    }


def build_hardware_feedback(
    analysis: dict[str, Any] | None,
    result: dict[str, Any] | None,
    repo_root: Path,
) -> str:
    parts: list[str] = []
    if analysis is not None and not analysis.get("passed", False):
        parts.append(
            "Hardware pre-synthesis screen failed:\n"
            + json.dumps(analysis, indent=2, sort_keys=True)
        )
    if result is not None:
        compact = {
            "correct": result.get("correct"),
            "synthesis_passed": result.get("synthesis_passed"),
            "vitis_synthesis_passed": result.get("vitis_synthesis_passed"),
            "status": result.get("status"),
            "seconds": result.get("seconds"),
            "metrics": result.get("metrics"),
        }
        parts.append("Hardware goal result summary:\n" + json.dumps(compact, indent=2))
        vitis_rel = result.get("logs", {}).get("vitis")
        if vitis_rel:
            log_path = repo_root / vitis_rel
            if log_path.exists():
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
                parts.append(
                    "Vitis/Vivado synthesis log summary:\n"
                    + json.dumps(summarize_vitis_log(log_text), indent=2, sort_keys=True)
                )
                tail = log_text[-4000:]
                if tail:
                    parts.append("Tail of Vitis/Vivado log:\n" + tail)
    if parts:
        parts.append(
            "Required repair for hardware mode: preserve the task interface and "
            "correctness, but implement a staged iterative/dataflow/hybrid NTT "
            "datapath with bounded butterfly units, pipelined modular "
            "multiplication, and explicit coefficient/twiddle storage. Do not "
            "compute the full transform inside one procedural task or one clock "
            "edge."
        )
    return "\n\n".join(parts)
