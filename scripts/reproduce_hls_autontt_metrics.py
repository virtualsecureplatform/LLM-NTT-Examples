#!/usr/bin/env python3
"""Fresh-clone reproducibility entry point for HLS/AutoNTT metric reports."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "reproduce-hls-autontt"
DEFAULT_SIF = "auto"
DEFAULT_XILINX_ROOT = Path("/home/opt/xilinx")
DEFAULT_VITIS_SETTINGS = "Vitis/2023.2/settings64.sh"


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def run_logged(
    cmd: list[str],
    *,
    log_path: Path,
    cwd: Path = REPO_ROOT,
    dry_run: bool = False,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = " ".join(shlex.quote(part) for part in cmd)
    print(rendered)
    if dry_run:
        log_path.write_text("$ " + rendered + "\nDRY RUN\n", encoding="utf-8")
        return
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + rendered + "\n")
        log.flush()
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit {completed.returncode}; see {relpath(log_path)}"
        )


def settings_path(xilinx_root: Path, vitis_settings: str) -> Path:
    settings = Path(vitis_settings).expanduser()
    if settings.is_absolute():
        return settings.resolve()
    return (xilinx_root / settings).resolve()


def resolve_sif(value: str) -> Path:
    if value != "auto":
        return Path(value).expanduser().resolve()
    env_value = os.environ.get("LLM_NTT_SIF")
    if env_value:
        return Path(env_value).expanduser().resolve()
    for candidate in (REPO_ROOT / "llm-ntt-rootless.sif", REPO_ROOT / "llm-ntt.sif"):
        if candidate.exists():
            return candidate.resolve()
    return (REPO_ROOT / "llm-ntt.sif").resolve()


def ensure_vitis_visible(xilinx_root: Path, vitis_settings: str) -> Path:
    settings = settings_path(xilinx_root, vitis_settings)
    if not settings.exists():
        raise FileNotFoundError(
            f"Vitis settings script not found: {settings}. "
            "Install/bind Vitis on the host or pass --xilinx-root/--vitis-settings."
        )
    return settings


def latest_subdir(root: Path) -> Path:
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no run directory under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def top_rtl_dirs_from_results(data: dict[str, Any]) -> list[Path]:
    dirs = []
    for report in data.get("hls_reports", {}).values():
        report_path = (REPO_ROOT / report).resolve() if not Path(report).is_absolute() else Path(report)
        if report_path.name.endswith("_csynth.xml"):
            dirs.append(report_path.parent.parent / "verilog")
    return dirs


def top_rtl_dirs_for_results(results_path: Path) -> list[Path]:
    return top_rtl_dirs_from_results(load_json(results_path))


def verify_generated_rtl(summary: dict[str, Any]) -> list[str]:
    checked: list[str] = []
    result_keys = ("results", "reference_results", "generated_results")
    summaries = summary.get("variants")
    if isinstance(summaries, list):
        for item in summaries:
            if not isinstance(item, dict):
                continue
            for key in result_keys:
                value = item.get(key)
                if value:
                    checked.extend(verify_generated_rtl(load_json(REPO_ROOT / value)))
        return checked

    for key in result_keys:
        value = summary.get(key)
        if not value:
            continue
        for rtl_dir in top_rtl_dirs_for_results(REPO_ROOT / value):
            if not rtl_dir.is_dir():
                raise FileNotFoundError(f"expected generated HLS RTL directory: {rtl_dir}")
            checked.append(relpath(rtl_dir))
    if "hls_reports" in summary:
        for rtl_dir in top_rtl_dirs_from_results(summary):
            if not rtl_dir.is_dir():
                raise FileNotFoundError(f"expected generated HLS RTL directory: {rtl_dir}")
            checked.append(relpath(rtl_dir))
    return checked


def comparison_from_path(path: Path) -> dict[str, Any]:
    comparison = load_json(path)
    comparison["_path"] = relpath(path)
    return comparison


def collect_comparisons(summary: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    if summary.get("comparison"):
        comparisons.append(comparison_from_path(REPO_ROOT / summary["comparison"]))
    variants = summary.get("variants")
    if isinstance(variants, list):
        for item in variants:
            if isinstance(item, dict) and item.get("comparison"):
                comparisons.append(comparison_from_path(REPO_ROOT / item["comparison"]))
    return comparisons


def metric_value(comparison: dict[str, Any], metric: str) -> Any:
    return comparison.get("resources", {}).get("metrics", {}).get(metric, {}).get("candidate")


def first_latency_totals(comparison: dict[str, Any]) -> tuple[Any, Any]:
    intt_total = None
    ntt_total = None
    groups = comparison.get("latency", {}).get("groups", {})
    if isinstance(groups, dict):
        for name, group in groups.items():
            if not isinstance(group, dict):
                continue
            total = group.get("candidate", {}).get("total_cycles")
            if name.endswith("_intt") or "_intt" in name:
                intt_total = total
            if name.endswith("_ntt") or "_ntt" in name:
                ntt_total = total
    return intt_total, ntt_total


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def build_report(
    *,
    run_root: Path,
    sif: Path,
    summaries: list[dict[str, Any]],
    rtl_dirs: list[str],
) -> str:
    comparisons: list[dict[str, Any]] = []
    for summary in summaries:
        comparisons.extend(collect_comparisons(summary))

    lines = [
        "# HLS AutoNTT Reproduction Report",
        "",
        f"- run root: `{relpath(run_root)}`",
        f"- SIF: `{sif}`",
        f"- HLS RTL directories checked: {len(rtl_dirs)}",
        "",
        "## AutoNTT Metrics",
        "",
        "| Task | INTT cycles | NTT cycles | LUT | FF | DSP | BRAM | URAM | fmax MHz | Score |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for comparison in comparisons:
        task = comparison.get("task_id", {}).get("candidate")
        intt_total, ntt_total = first_latency_totals(comparison)
        timing = comparison.get("timing", {}).get("fmax_mhz", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{task}`",
                    fmt(intt_total),
                    fmt(ntt_total),
                    fmt(metric_value(comparison, "vitis_lut")),
                    fmt(metric_value(comparison, "vitis_ff")),
                    fmt(metric_value(comparison, "vitis_dsp")),
                    fmt(metric_value(comparison, "vitis_bram_tile")),
                    fmt(metric_value(comparison, "vitis_uram")),
                    fmt(timing.get("candidate")),
                    fmt(comparison.get("resource_aware_score")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## HLS RTL",
            "",
            "Vitis HLS `csynth_design` emitted these RTL directories after the "
            "functional HLS C++ checks passed:",
            "",
        ]
    )
    for rtl_dir in sorted(set(rtl_dirs)):
        lines.append(f"- `{rtl_dir}`")
    return "\n".join(lines) + "\n"


def build_sif(args: argparse.Namespace, run_root: Path) -> None:
    if args.skip_sif_build and not args.sif.exists():
        raise FileNotFoundError(f"--skip-sif-build was set but SIF is missing: {args.sif}")
    if args.skip_sif_build:
        print(f"Using existing SIF: {args.sif}")
        return
    if args.sif.exists() and not args.force_sif_build:
        print(f"Using existing SIF: {args.sif}")
        return

    cmd = [
        "scripts/build_llm_ntt_sif.sh",
        "--output",
        str(args.sif),
        "--processors",
        str(args.sif_processors),
    ]
    if args.sudo_sif_build:
        cmd.append("--sudo")
    if args.with_tapa_runtime:
        cmd.extend(["--with-tapa-runtime", "--tapa-build-jobs", str(args.tapa_build_jobs)])
    run_logged(cmd, log_path=run_root / "logs" / "build-sif.log", dry_run=args.dry_run)


def run(args: argparse.Namespace) -> Path:
    run_name = args.run_name or time.strftime("%Y%m%d-%H%M%S")
    run_root = args.output_root / run_name
    run_root.mkdir(parents=True, exist_ok=False)

    if not args.skip_submodule_update:
        run_logged(
            ["git", "submodule", "update", "--init", "--recursive"],
            log_path=run_root / "logs" / "submodule-update.log",
            dry_run=args.dry_run,
        )

    build_sif(args, run_root)
    settings = ensure_vitis_visible(args.xilinx_root, args.vitis_settings)
    print(f"Using Vitis settings: {settings}")

    summaries: list[dict[str, Any]] = []

    if "small" in args.targets:
        small_root = run_root / "small-variants"
        cmd = [
            "scripts/run_small_variant_hls_synth_compare.py",
            "--variants",
            "all",
            "--output-root",
            str(small_root),
            "--sif",
            str(args.sif),
            "--xilinx-root",
            str(args.xilinx_root),
            "--vitis-settings",
            str(settings),
            "--vitis-timeout",
            str(args.vitis_timeout),
        ]
        run_logged(cmd, log_path=run_root / "logs" / "small-variants.log", dry_run=args.dry_run)
        if not args.dry_run:
            summaries.append(load_json(latest_subdir(small_root) / "summary.json"))

    if "full-yata" in args.targets:
        yata_root = run_root / "full-yata"
        cmd = [
            "scripts/run_yata_hls_synth_compare.py",
            "--output-root",
            str(yata_root),
            "--sif",
            str(args.sif),
            "--xilinx-root",
            str(args.xilinx_root),
            "--vitis-settings",
            str(settings),
            "--vitis-timeout",
            str(args.vitis_timeout),
        ]
        run_logged(cmd, log_path=run_root / "logs" / "full-yata.log", dry_run=args.dry_run)
        if not args.dry_run:
            summaries.append(load_json(latest_subdir(yata_root) / "summary.json"))

    rtl_dirs: list[str] = []
    if not args.dry_run:
        for summary in summaries:
            rtl_dirs.extend(verify_generated_rtl(summary))
        report = build_report(run_root=run_root, sif=args.sif, summaries=summaries, rtl_dirs=rtl_dirs)
        (run_root / "report.md").write_text(report, encoding="utf-8")
        write_json(
            run_root / "summary.json",
            {
                "run_dir": relpath(run_root),
                "sif": str(args.sif),
                "targets": args.targets,
                "summaries": summaries,
                "generated_rtl_dirs": sorted(set(rtl_dirs)),
                "report": relpath(run_root / "report.md"),
            },
        )
        print(f"Wrote {relpath(run_root / 'report.md')}")
    else:
        write_json(run_root / "summary.json", {"dry_run": True, "targets": args.targets})

    return run_root


def parse_targets(value: str) -> list[str]:
    if value == "all":
        return ["small", "full-yata"]
    allowed = {"small", "full-yata"}
    targets = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(targets) - allowed)
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown target(s): {', '.join(unknown)}")
    if not targets:
        raise argparse.ArgumentTypeError("at least one target is required")
    return targets


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "From a fresh clone, build/reuse the SIF, run generated HLS flows, "
            "verify generated RTL exists, and report AutoNTT metrics."
        )
    )
    parser.add_argument("--targets", type=parse_targets, default=parse_targets("all"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-name")
    parser.add_argument(
        "--sif",
        default=DEFAULT_SIF,
        help=(
            "SIF path, or auto. Auto uses LLM_NTT_SIF, then an existing "
            "llm-ntt-rootless.sif, then llm-ntt.sif; fresh clones build llm-ntt.sif."
        ),
    )
    parser.add_argument("--skip-sif-build", action="store_true")
    parser.add_argument("--force-sif-build", action="store_true")
    parser.add_argument("--sudo-sif-build", action="store_true")
    parser.add_argument("--with-tapa-runtime", action="store_true")
    parser.add_argument("--tapa-build-jobs", type=int, default=4)
    parser.add_argument("--sif-processors", type=int, default=1)
    parser.add_argument("--skip-submodule-update", action="store_true")
    parser.add_argument("--xilinx-root", type=Path, default=Path(os.environ.get("XILINX_ROOT", DEFAULT_XILINX_ROOT)))
    parser.add_argument("--vitis-settings", default=os.environ.get("VITIS_SETTINGS", DEFAULT_VITIS_SETTINGS))
    parser.add_argument("--vitis-timeout", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    args.output_root = args.output_root.expanduser().resolve()
    args.sif = resolve_sif(args.sif)
    args.xilinx_root = args.xilinx_root.expanduser().resolve()
    try:
        run(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
