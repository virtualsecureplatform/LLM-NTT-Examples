#!/usr/bin/env python3
"""Compare two evaluator result JSON files with AutoNTT-style metrics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


RESOURCE_KEYS = (
    "vitis_lut",
    "vitis_ff",
    "vitis_dsp",
    "vitis_bram_tile",
    "vitis_uram",
)

RESOURCE_WEIGHTS = {
    "lut": 0.35,
    "ff": 0.20,
    "dsp": 0.30,
    "memory": 0.15,
}


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def compact_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    if value.is_integer():
        return int(value)
    return value


def divide(candidate: float | None, reference: float | None) -> float | None:
    if candidate is None or reference is None:
        return None
    if reference == 0:
        return 1.0 if candidate == 0 else None
    return candidate / reference


def inverse_divide(candidate: float | None, reference: float | None) -> float | None:
    if candidate is None or reference is None or candidate == 0:
        return None
    return reference / candidate


def geomean(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0 and math.isfinite(value)]
    if not positive:
        return None
    return math.exp(sum(math.log(value) for value in positive) / len(positive))


def metric_dict(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics", {})
    if not isinstance(metrics, dict):
        return {}
    return metrics


def latency_groups(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    suffixes = {
        "_input_cycles": "input_cycles",
        "_output_cycles": "output_cycles",
        "_max_wait_cycles": "wait_cycles",
        "_wait_cycles": "wait_cycles",
    }
    for key, value in metrics.items():
        amount = numeric(value)
        if amount is None:
            continue
        for suffix, field in suffixes.items():
            if not key.endswith(suffix):
                continue
            prefix = key[: -len(suffix)]
            group = groups.setdefault(prefix, {})
            if field == "wait_cycles":
                current = group.get(field)
                if current is None or suffix == "_max_wait_cycles":
                    group[field] = amount
                    group["wait_metric"] = key
            else:
                group[field] = amount
                group[f"{field[:-7]}_metric"] = key
            break
    for group in groups.values():
        input_cycles = group.get("input_cycles")
        wait_cycles = group.get("wait_cycles")
        output_cycles = group.get("output_cycles")
        if (
            isinstance(input_cycles, float)
            and isinstance(wait_cycles, float)
            and isinstance(output_cycles, float)
        ):
            group["total_cycles"] = input_cycles + wait_cycles + output_cycles
    return groups


def compare_latency(
    reference_metrics: dict[str, Any], candidate_metrics: dict[str, Any]
) -> dict[str, Any]:
    reference_groups = latency_groups(reference_metrics)
    candidate_groups = latency_groups(candidate_metrics)
    prefixes = sorted(set(reference_groups) | set(candidate_groups))
    groups: dict[str, Any] = {}
    latency_scores: list[float] = []

    for prefix in prefixes:
        ref_group = reference_groups.get(prefix, {})
        cand_group = candidate_groups.get(prefix, {})
        comparison: dict[str, Any] = {
            "reference": {
                key: compact_number(ref_group.get(key))
                for key in (
                    "input_cycles",
                    "wait_cycles",
                    "output_cycles",
                    "total_cycles",
                )
                if ref_group.get(key) is not None
            },
            "candidate": {
                key: compact_number(cand_group.get(key))
                for key in (
                    "input_cycles",
                    "wait_cycles",
                    "output_cycles",
                    "total_cycles",
                )
                if cand_group.get(key) is not None
            },
            "ratios": {},
        }
        for key in ("input_cycles", "wait_cycles", "output_cycles"):
            ratio = divide(cand_group.get(key), ref_group.get(key))
            if ratio is not None:
                comparison["ratios"][key] = ratio
        latency_score = inverse_divide(
            cand_group.get("total_cycles"), ref_group.get("total_cycles")
        )
        if latency_score is not None:
            comparison["latency_score"] = latency_score
            latency_scores.append(latency_score)
        groups[prefix] = comparison

    return {
        "groups": groups,
        "aggregate_latency_score": geomean(latency_scores),
    }


def compare_resources(
    reference_metrics: dict[str, Any], candidate_metrics: dict[str, Any]
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key in RESOURCE_KEYS:
        reference_value = numeric(reference_metrics.get(key))
        candidate_value = numeric(candidate_metrics.get(key))
        metrics[key] = {
            "reference": compact_number(reference_value),
            "candidate": compact_number(candidate_value),
            "candidate_over_reference": divide(candidate_value, reference_value),
        }

    reference_memory = sum(
        numeric(reference_metrics.get(key)) or 0.0
        for key in ("vitis_bram_tile", "vitis_uram")
    )
    candidate_memory = sum(
        numeric(candidate_metrics.get(key)) or 0.0
        for key in ("vitis_bram_tile", "vitis_uram")
    )
    memory_ratio = divide(candidate_memory, reference_memory)
    ratios = {
        "lut": metrics["vitis_lut"]["candidate_over_reference"],
        "ff": metrics["vitis_ff"]["candidate_over_reference"],
        "dsp": metrics["vitis_dsp"]["candidate_over_reference"],
        "memory": memory_ratio,
    }
    resource_penalty = None
    if all(value is not None for value in ratios.values()):
        resource_penalty = sum(
            RESOURCE_WEIGHTS[key] * float(value) for key, value in ratios.items()
        )

    return {
        "metrics": metrics,
        "memory": {
            "reference": compact_number(reference_memory),
            "candidate": compact_number(candidate_memory),
            "candidate_over_reference": memory_ratio,
        },
        "weights": RESOURCE_WEIGHTS,
        "resource_penalty": resource_penalty,
    }


def compare_timing(
    reference_metrics: dict[str, Any], candidate_metrics: dict[str, Any]
) -> dict[str, Any]:
    reference_fmax = numeric(reference_metrics.get("vitis_fmax_mhz"))
    candidate_fmax = numeric(candidate_metrics.get("vitis_fmax_mhz"))
    reference_wns = numeric(reference_metrics.get("vitis_timing_wns_ns"))
    candidate_wns = numeric(candidate_metrics.get("vitis_timing_wns_ns"))
    return {
        "fmax_mhz": {
            "reference": compact_number(reference_fmax),
            "candidate": compact_number(candidate_fmax),
            "candidate_over_reference": divide(candidate_fmax, reference_fmax),
        },
        "wns_ns": {
            "reference": compact_number(reference_wns),
            "candidate": compact_number(candidate_wns),
            "candidate_minus_reference": (
                candidate_wns - reference_wns
                if candidate_wns is not None and reference_wns is not None
                else None
            ),
        },
    }


def compare_results(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    reference_path: str = "",
    candidate_path: str = "",
) -> dict[str, Any]:
    reference_metrics = metric_dict(reference)
    candidate_metrics = metric_dict(candidate)
    latency = compare_latency(reference_metrics, candidate_metrics)
    resources = compare_resources(reference_metrics, candidate_metrics)
    timing = compare_timing(reference_metrics, candidate_metrics)

    resource_aware_score = None
    if (
        latency["aggregate_latency_score"] is not None
        and resources["resource_penalty"] not in (None, 0)
    ):
        resource_aware_score = (
            latency["aggregate_latency_score"] / resources["resource_penalty"]
        )

    return {
        "schema": "llm-ntt-autontt-comparison-v1",
        "task_id": {
            "reference": reference.get("task_id"),
            "candidate": candidate.get("task_id"),
            "match": reference.get("task_id") == candidate.get("task_id"),
        },
        "paths": {
            "reference": reference_path,
            "candidate": candidate_path,
        },
        "correctness": {
            "reference_correct": reference.get("correct"),
            "candidate_correct": candidate.get("correct"),
            "both_correct": bool(reference.get("correct"))
            and bool(candidate.get("correct")),
            "reference_vitis_synthesis_passed": reference.get(
                "vitis_synthesis_passed"
            ),
            "candidate_vitis_synthesis_passed": candidate.get(
                "vitis_synthesis_passed"
            ),
            "both_vitis_synthesis_passed": bool(
                reference.get("vitis_synthesis_passed")
            )
            and bool(candidate.get("vitis_synthesis_passed")),
        },
        "latency": latency,
        "resources": resources,
        "timing": timing,
        "resource_aware_score": resource_aware_score,
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def format_table(comparison: dict[str, Any]) -> str:
    lines = []
    task = comparison["task_id"]
    lines.append(
        f"Task: reference={task['reference']} candidate={task['candidate']} "
        f"match={task['match']}"
    )
    correctness = comparison["correctness"]
    lines.append(
        "Correctness: "
        f"reference={correctness['reference_correct']} "
        f"candidate={correctness['candidate_correct']} "
        f"vitis_reference={correctness['reference_vitis_synthesis_passed']} "
        f"vitis_candidate={correctness['candidate_vitis_synthesis_passed']}"
    )
    lines.append("")
    lines.append("Latency:")
    lines.append("group,reference_total,candidate_total,latency_score")
    for group, data in comparison["latency"]["groups"].items():
        lines.append(
            ",".join(
                [
                    group,
                    fmt(data["reference"].get("total_cycles")),
                    fmt(data["candidate"].get("total_cycles")),
                    fmt(data.get("latency_score")),
                ]
            )
        )
    lines.append(
        f"aggregate_latency_score,{fmt(comparison['latency']['aggregate_latency_score'])}"
    )
    lines.append("")
    lines.append("Resources:")
    lines.append("metric,reference,candidate,candidate_over_reference")
    for key, data in comparison["resources"]["metrics"].items():
        lines.append(
            ",".join(
                [
                    key,
                    fmt(data["reference"]),
                    fmt(data["candidate"]),
                    fmt(data["candidate_over_reference"]),
                ]
            )
        )
    memory = comparison["resources"]["memory"]
    lines.append(
        ",".join(
            [
                "memory_bram_plus_uram",
                fmt(memory["reference"]),
                fmt(memory["candidate"]),
                fmt(memory["candidate_over_reference"]),
            ]
        )
    )
    lines.append(
        f"resource_penalty,{fmt(comparison['resources']['resource_penalty'])}"
    )
    lines.append(f"resource_aware_score,{fmt(comparison['resource_aware_score'])}")
    lines.append("")
    timing = comparison["timing"]
    lines.append("Timing:")
    lines.append(
        "fmax_mhz,"
        f"{fmt(timing['fmax_mhz']['reference'])},"
        f"{fmt(timing['fmax_mhz']['candidate'])},"
        f"{fmt(timing['fmax_mhz']['candidate_over_reference'])}"
    )
    lines.append(
        "wns_ns,"
        f"{fmt(timing['wns_ns']['reference'])},"
        f"{fmt(timing['wns_ns']['candidate'])},"
        f"delta={fmt(timing['wns_ns']['candidate_minus_reference'])}"
    )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare evaluator results using AutoNTT-style metrics."
    )
    parser.add_argument("--reference", required=True, help="Reference results.json")
    parser.add_argument("--candidate", required=True, help="Candidate results.json")
    parser.add_argument("--output", help="Optional JSON comparison output path")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON to stdout instead of the compact table.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    reference_path = Path(args.reference).expanduser().resolve()
    candidate_path = Path(args.candidate).expanduser().resolve()
    comparison = compare_results(
        load_json(reference_path),
        load_json(candidate_path),
        str(reference_path),
        str(candidate_path),
    )
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(comparison, indent=2, sort_keys=True))
    else:
        print(format_table(comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
