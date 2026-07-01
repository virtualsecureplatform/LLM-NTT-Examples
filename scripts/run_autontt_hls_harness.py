#!/usr/bin/env python3
"""Run the adjacent AutoNTT HLS generator and capture its artifacts.

This is intentionally separate from the Verilog candidate evaluator. AutoNTT
emits TAPA/Vitis HLS C++ kernels, not the Verilog top modules used by the
LLM-NTT task manifests. The script records generated HLS designs or the
environmental blocker that prevents generation.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTONTT_ROOT = REPO_ROOT.parent / "AutoNTT" / "automation_framework"
HOGE_CUSTOM_KERNEL = (
    REPO_ROOT / "examples" / "autontt" / "custom_reductions" / "hoge_p64" / "custom_red_kernel.txt"
)
HOGE_CUSTOM_HOST = (
    REPO_ROOT / "examples" / "autontt" / "custom_reductions" / "hoge_p64" / "custom_red_host.txt"
)
REDUCTION_NAMES = {
    "N": "NAIVE_RED",
    "B": "BARRETT",
    "M": "MONTGOMERY",
    "WLM": "WLM",
    "C": "CUSTOM_REDUCTION",
}
DEFAULT_CUSTOM_BU_ESTIMATE = "15,32,2345,1481"
DEFAULT_ARCH_TYPE = "ID"
VALID_ARCH_TYPES = ("I", "D", "H")


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@contextmanager
def locked_autontt_root(autontt_root: Path):
    digest = hashlib.sha256(str(autontt_root).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"llm_ntt_autontt_{digest}.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def newest_platform(default: str = "xilinx_u280_gen3x16_xdma_1_202211_1") -> str:
    platform_root = Path("/opt/xilinx/platforms")
    if (platform_root / default).exists():
        return default
    candidates = sorted(p.name for p in platform_root.glob("xilinx_*") if p.is_dir())
    if candidates:
        return candidates[-1]
    return default


def tree_mtime(path: Path) -> float:
    return max((item.stat().st_mtime for item in path.rglob("*")), default=path.stat().st_mtime)


def validate_arch_type(value: str) -> str:
    result = ""
    for char in value.strip().upper():
        if char.isspace() or char == ",":
            continue
        if char not in VALID_ARCH_TYPES:
            raise argparse.ArgumentTypeError(
                f"invalid architecture type {char!r}; expected I, D, H, or a combination"
            )
        if char not in result:
            result += char
    if not result:
        raise argparse.ArgumentTypeError("architecture type cannot be empty")
    return result


def requested_arch_types(arch_type: str) -> list[str]:
    return list(validate_arch_type(arch_type))


def expected_design_prefix(args: argparse.Namespace, arch_type: str) -> str:
    reduction_name = REDUCTION_NAMES[args.modmul_type]
    return f"AutoNTT_{arch_type}__N_{args.poly_size}__q_{args.mod_size}__red_{reduction_name}__"


def expected_design_prefixes(args: argparse.Namespace) -> list[str]:
    return [expected_design_prefix(args, arch) for arch in requested_arch_types(args.arch_type)]


def find_recent_design_dirs(tool_outputs: Path, prefixes: str | list[str], since: float) -> list[Path]:
    if not tool_outputs.exists():
        return []
    result: list[Path] = []
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    seen: set[Path] = set()
    for prefix in prefixes:
        for path in sorted(tool_outputs.glob(f"{prefix}*")):
            if not path.is_dir() or path in seen:
                continue
            if tree_mtime(path) >= since:
                result.append(path)
                seen.add(path)
    return result


def copy_artifact_dir(source: Path, artifact_root: Path) -> Path:
    destination = artifact_root / source.name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def parse_custom_bu_estimate(raw: str) -> dict[str, int]:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 4:
        raise ValueError(
            "--custom-bu-estimate must have four comma-separated integers: "
            "pipeline_depth,dsp,lut,ff"
        )
    pipeline_depth, dsp, lut, ff = (int(part) for part in parts)
    if pipeline_depth < 0 or dsp <= 0 or lut <= 0 or ff <= 0:
        raise ValueError("--custom-bu-estimate values must be non-negative depth and positive dsp/lut/ff")
    return {
        "pipeline_depth": pipeline_depth,
        "dsp": dsp,
        "lut": lut,
        "ff": ff,
    }


def write_estimate_launcher(run_root: Path, autontt_root: Path, estimate: dict[str, int]) -> Path:
    launcher = run_root / "autontt_with_custom_bu_estimate.py"
    launcher.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import sys",
                "from pathlib import Path",
                "",
                f"AUTONTT_ROOT = Path({str(autontt_root)!r})",
                f"ESTIMATE = {estimate!r}",
                "sys.path.insert(0, str(AUTONTT_ROOT))",
                "",
                "from dse.common.BU import BU_models",
                "from dse import dse_compute",
                "",
                "",
                "def estimated_custom_bu_attributes(_params):",
                "    print(",
                "        '[LLM-NTT] Using estimated custom BU attributes: '",
                "        f\"depth={ESTIMATE['pipeline_depth']},\"",
                "        f\"dsp={ESTIMATE['dsp']},\"",
                "        f\"lut={ESTIMATE['lut']},\"",
                "        f\"ff={ESTIMATE['ff']}\"",
                "    )",
                "    return (",
                "        ESTIMATE['pipeline_depth'],",
                "        ESTIMATE['dsp'],",
                "        ESTIMATE['lut'],",
                "        ESTIMATE['ff'],",
                "    )",
                "",
                "",
                "BU_models.get_custom_reduction_BU_attributes = estimated_custom_bu_attributes",
                "dse_compute.get_custom_reduction_BU_attributes = estimated_custom_bu_attributes",
                "",
                "import AutoNTT",
                "",
                "AutoNTT.main()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return launcher


def summarize_hls_dir(path: Path) -> dict[str, Any]:
    files = sorted(item.name for item in path.iterdir() if item.is_file())
    kernel = path / "ntt_kernel.cpp"
    header = path / "ntt.h"
    signature = ""
    if kernel.exists():
        text = kernel.read_text(encoding="utf-8", errors="replace")
        marker = "void NTT_kernel("
        start = text.find(marker)
        if start >= 0:
            end = text.find("{", start)
            if end >= 0:
                signature = text[start:end].strip()
    constants: dict[str, str] = {}
    if header.exists():
        for line in header.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            for name in ("logN", "N", "logBU", "NUM_BU", "WORD_SIZE", "POLY_LS_PORTS", "TF_PORTS"):
                if stripped.startswith(f"const ") and f" {name}=" in stripped:
                    constants[name] = stripped
    return {
        "path": str(path),
        "files": files,
        "ntt_kernel_signature": signature,
        "constants": constants,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run AutoNTT HLS generation and capture artifacts for LLM-NTT adapter work."
    )
    parser.add_argument("--autontt-root", default=str(DEFAULT_AUTONTT_ROOT))
    parser.add_argument("--output-root", default="build/autontt-hls-runs")
    parser.add_argument("--poly-size", default="1024")
    parser.add_argument("--mod-size", default="64")
    parser.add_argument(
        "--arch-type",
        type=validate_arch_type,
        default=DEFAULT_ARCH_TYPE,
        help=(
            "AutoNTT architecture filter. Defaults to ID so the HLS path tries "
            "DataFlow while retaining the iterative fallback. Use D to force "
            "DataFlow only, or IDH to match AutoNTT's full search."
        ),
    )
    parser.add_argument(
        "--modmul-type",
        choices=("B", "M", "WLM", "C", "N"),
        default="C",
        help="AutoNTT reduction type. C uses the HOGE p64 custom reduction files by default.",
    )
    parser.add_argument("--platform", default="")
    parser.add_argument("--resources", default="fpga_resources.json")
    parser.add_argument("--parallel-limbs", default="")
    parser.add_argument("--latency-target", default="")
    parser.add_argument("--throughput-target", default="")
    parser.add_argument("--custom-mod-kernel", default=str(HOGE_CUSTOM_KERNEL))
    parser.add_argument("--custom-mod-host", default=str(HOGE_CUSTOM_HOST))
    parser.add_argument(
        "--custom-bu-mode",
        choices=("estimate", "probe"),
        default="estimate",
        help=(
            "For custom reductions, estimate bypasses AutoNTT's TAPA/Autobridge "
            "BU measurement probe and uses --custom-bu-estimate for codegen. "
            "Probe runs the original AutoNTT C-sim/TAPA measurement path."
        ),
    )
    parser.add_argument(
        "--custom-bu-estimate",
        default=DEFAULT_CUSTOM_BU_ESTIMATE,
        help="pipeline_depth,dsp,lut,ff used when --modmul-type C and --custom-bu-mode estimate.",
    )
    parser.add_argument("--verbose", default="0")
    parser.add_argument(
        "--allow-failure",
        action="store_true",
        help="Return success after writing summary even if AutoNTT exits non-zero.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    autontt_root = Path(args.autontt_root).expanduser().resolve()
    if not autontt_root.exists():
        raise FileNotFoundError(f"AutoNTT root not found: {autontt_root}")

    run_root = (REPO_ROOT / args.output_root / timestamp()).resolve()
    artifact_root = run_root / "artifacts"
    run_root.mkdir(parents=True, exist_ok=True)
    platform = args.platform or newest_platform()
    design_prefixes = expected_design_prefixes(args)

    autontt_args = [
        "--poly_size",
        str(args.poly_size),
        "--mod_size",
        str(args.mod_size),
        "--resources",
        str(args.resources),
        "--arch_type",
        str(args.arch_type),
        "--modmul_type",
        str(args.modmul_type),
        "--platform",
        platform,
        "--verbose",
        str(args.verbose),
    ]
    if args.parallel_limbs:
        autontt_args.extend(["--parallel_limbs", args.parallel_limbs])
    if args.latency_target:
        autontt_args.extend(["--latency_target", args.latency_target])
    if args.throughput_target:
        autontt_args.extend(["--throughput_target", args.throughput_target])
    if args.modmul_type == "C":
        autontt_args.extend(["--custom_mod_kernel", str(Path(args.custom_mod_kernel).resolve())])
        autontt_args.extend(["--custom_mod_host", str(Path(args.custom_mod_host).resolve())])

    custom_bu_estimate = None
    custom_bu_mode = "none"
    if args.modmul_type == "C":
        custom_bu_mode = args.custom_bu_mode
        if args.custom_bu_mode == "estimate":
            custom_bu_estimate = parse_custom_bu_estimate(args.custom_bu_estimate)

    if custom_bu_estimate is not None:
        launcher = write_estimate_launcher(run_root, autontt_root, custom_bu_estimate)
        cmd = [sys.executable, str(launcher), *autontt_args]
    else:
        cmd = [sys.executable, "AutoNTT.py", *autontt_args]

    write_json(
        run_root / "request.json",
        {
            "command": cmd,
            "autontt_args": autontt_args,
            "requested_architectures": requested_arch_types(args.arch_type),
            "expected_design_prefixes": design_prefixes,
            "cwd": str(autontt_root),
            "platform": platform,
            "output_root": str(run_root),
            "custom_bu_mode": custom_bu_mode,
            "custom_bu_estimate": custom_bu_estimate,
        },
    )

    copied_designs: list[Path] = []
    copied_temp_design = None
    with locked_autontt_root(autontt_root):
        start = time.time() - 1.0
        proc = subprocess.run(
            cmd,
            cwd=autontt_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        (run_root / "autontt.stdout").write_text(proc.stdout, encoding="utf-8")

        if proc.returncode == 0:
            for design_dir in find_recent_design_dirs(autontt_root / "tool_outputs", design_prefixes, start):
                copied_designs.append(copy_artifact_dir(design_dir, artifact_root))

        temp_design = autontt_root / "temp_design"
        if (
            args.modmul_type == "C"
            and custom_bu_mode == "probe"
            and temp_design.exists()
            and temp_design.is_dir()
            and tree_mtime(temp_design) >= start
        ):
            copied_temp_design = copy_artifact_dir(temp_design, artifact_root)

    status = "generated_hls" if proc.returncode == 0 and copied_designs else "failed"
    likely_blocker = ""
    if proc.returncode != 0:
        lower = proc.stdout.lower()
        if "c simulation failed" in lower and copied_temp_design is not None:
            likely_blocker = (
                "AutoNTT custom-reduction BU probe failed. On this host the "
                "captured temp_design C-sim compile is missing TAPA/gflags "
                "headers and libraries, so final HLS codegen for the custom "
                "HOGE reduction did not complete."
            )
        elif "platform" in lower and "not found" in lower:
            likely_blocker = "Requested Xilinx platform directory was not found under /opt/xilinx/platforms."

    summary = {
        "schema": "llm-ntt-autontt-hls-run-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "ok": status == "generated_hls",
        "autontt_returncode": proc.returncode,
        "likely_blocker": likely_blocker,
        "command": cmd,
        "autontt_args": autontt_args,
        "requested_architectures": requested_arch_types(args.arch_type),
        "expected_design_prefixes": design_prefixes,
        "autontt_root": str(autontt_root),
        "run_root": str(run_root),
        "stdout": str(run_root / "autontt.stdout"),
        "custom_bu_mode": custom_bu_mode,
        "custom_bu_estimate": custom_bu_estimate,
        "custom_bu_note": (
            "Custom-reduction BU attributes are estimates used to unblock AutoNTT HLS "
            "source generation; they are not measured synthesis results."
            if custom_bu_estimate is not None
            else ""
        ),
        "designs": [summarize_hls_dir(path) for path in copied_designs],
        "temp_design": summarize_hls_dir(copied_temp_design) if copied_temp_design else None,
        "adapter_gap": (
            "AutoNTT emits TAPA/Vitis HLS mmap kernels named NTT_kernel. "
            "LLM-NTT tests consume Verilog task tops such as INTTWrap, "
            "ExternalProductWrap, NTTidPackedTop, and YataRainttTop. Passing "
            "the LLM-NTT tests from this path still requires HLS-to-RTL "
            "synthesis plus a protocol/order adapter."
        ),
    }
    write_json(run_root / "summary.json", summary)

    print(f"status: {status}")
    print(f"summary: {run_root / 'summary.json'}")
    if likely_blocker:
        print(f"blocker: {likely_blocker}")
    return 0 if (summary["ok"] or args.allow_failure) else proc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
