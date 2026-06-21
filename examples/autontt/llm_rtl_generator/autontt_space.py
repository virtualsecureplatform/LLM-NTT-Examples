"""AutoNTT-style design-point generation.

This is not a port of AutoNTT's HLS generator. It maps LLM-NTT tasks onto the
same high-level knobs used by AutoNTT: architecture family, parallelism, radix,
and modular multiplication strategy.
"""

from __future__ import annotations

from typing import Any


ARCHITECTURES = {
    "I": {
        "family": "iterative",
        "description": "reuse a smaller butterfly array across stages",
    },
    "D": {
        "family": "dataflow",
        "description": "pipeline stage groups with streaming buffers",
    },
    "H": {
        "family": "hybrid",
        "description": "unroll a subset of stages and reuse the pipeline",
    },
}

MODMUL = {
    "B": "Barrett reduction",
    "M": "Montgomery reduction",
    "WLM": "word-level Montgomery reduction",
    "N": "naive product/reduction baseline",
    "C": "prime-specific custom reduction",
}


def _word_bits(task: dict[str, Any]) -> int:
    params = task.get("parameters", {})
    for key in ("word_bits", "word_bits_internal", "mod_size"):
        if key in params:
            return int(params[key])
    modulus = int(str(params.get("modulus", "0")), 0)
    return max(1, modulus.bit_length())


def _lanes(task: dict[str, Any]) -> int:
    params = task.get("parameters", {})
    if "lanes" in params:
        return int(params["lanes"])
    n = int(params.get("N", 1))
    cycles = int(params.get("stream_cycles", n))
    return max(1, n // max(1, cycles))


def _default_modmul_types(task: dict[str, Any]) -> list[str]:
    params = task.get("parameters", {})
    modulus_hex = str(params.get("modulus_hex", "")).lower()
    n = int(params.get("N", 0))
    if modulus_hex == "0xffffffff00000001":
        return ["C", "WLM", "M", "B"]
    if modulus_hex in ("0x02710001", "0x2710001") or n == 512:
        return ["C", "B", "N"]
    return ["B", "M", "N"]


def _normalise_modmul_types(value: str | None, task: dict[str, Any]) -> list[str]:
    if value is None or value.strip().upper() == "AUTO":
        return _default_modmul_types(task)
    result: list[str] = []
    for item in value.replace(",", " ").split():
        code = item.strip().upper()
        if not code:
            continue
        if code not in MODMUL:
            raise ValueError(f"unknown modmul type {code!r}; expected one of {sorted(MODMUL)}")
        result.append(code)
    return result or _default_modmul_types(task)


def _normalise_arch_types(value: str) -> list[str]:
    result: list[str] = []
    for char in value.upper():
        if char.isspace() or char == ",":
            continue
        if char not in ARCHITECTURES:
            raise ValueError(
                f"unknown architecture type {char!r}; expected I, D, H, or a combination"
            )
        if char not in result:
            result.append(char)
    return result or ["I", "D", "H"]


def _autontt_command(task: dict[str, Any], arch: str, modmul: str) -> list[str] | None:
    params = task.get("parameters", {})
    n = int(params.get("N", 0))
    if n < 1024:
        return None
    mod_size = _word_bits(task)
    cmd = [
        "python3",
        "AutoNTT.py",
        "--poly_size",
        str(n),
        "--mod_size",
        str(mod_size),
        "--resources",
        "fpga_resources.json",
        "--arch_type",
        arch,
        "--modmul_type",
        modmul,
    ]
    if modmul == "C" and str(params.get("modulus_hex", "")).lower() == "0xffffffff00000001":
        cmd.extend(
            [
                "--custom_mod_kernel",
                "../../LLM-NTT-Examples/examples/autontt/custom_reductions/"
                "hoge_p64/custom_red_kernel.txt",
                "--custom_mod_host",
                "../../LLM-NTT-Examples/examples/autontt/custom_reductions/"
                "hoge_p64/custom_red_host.txt",
            ]
        )
    return cmd


def generate_search_points(
    task: dict[str, Any],
    arch_types: str = "IDH",
    modmul_types: str | None = None,
    strategy: str = "hardware",
) -> list[dict[str, Any]]:
    params = task.get("parameters", {})
    if strategy == "behavioral_reference":
        return [
            {
                "name": "behavioral_reference",
                "strategy": strategy,
                "architecture_code": "SIM",
                "architecture_family": "behavioral_reference",
                "architecture_description": "prioritize a compact model that passes tests",
                "modmul_type": "N",
                "modmul_description": "simulation-oriented arithmetic",
                "poly_size": int(params.get("N", 0)),
                "word_bits": _word_bits(task),
                "lanes": _lanes(task),
                "radix": int(params.get("radix", max(2, _lanes(task)))),
                "butterfly_budget": 1,
                "pipeline_depth_hint": "as needed for the task handshake",
                "twiddle_strategy": "small ROM or generated constants",
                "buffer_strategy": "simple arrays/registers",
                "autontt_command": None,
            }
        ]

    points: list[dict[str, Any]] = []
    lanes = _lanes(task)
    radix = int(params.get("radix", max(2, lanes)))
    for arch in _normalise_arch_types(arch_types):
        for modmul in _normalise_modmul_types(modmul_types, task):
            family = ARCHITECTURES[arch]["family"]
            if arch == "I":
                butterfly_budget = max(1, lanes // 8)
                buffer_strategy = "single or ping-pong coefficient memory"
                pipeline_depth = "short arithmetic pipeline, stage loop controller"
            elif arch == "D":
                butterfly_budget = max(1, lanes)
                buffer_strategy = "stage-local streaming and transpose buffers"
                pipeline_depth = "deep enough to accept one stream word per cycle"
            else:
                butterfly_budget = max(1, lanes // 2)
                buffer_strategy = "banked buffers around an unrolled stage group"
                pipeline_depth = "moderate, with explicit valid-delay alignment"
            points.append(
                {
                    "name": f"{family}_{modmul.lower()}_r{radix}_l{lanes}",
                    "strategy": strategy,
                    "architecture_code": arch,
                    "architecture_family": family,
                    "architecture_description": ARCHITECTURES[arch]["description"],
                    "modmul_type": modmul,
                    "modmul_description": MODMUL[modmul],
                    "poly_size": int(params.get("N", 0)),
                    "word_bits": _word_bits(task),
                    "lanes": lanes,
                    "radix": radix,
                    "butterfly_budget": butterfly_budget,
                    "pipeline_depth_hint": pipeline_depth,
                    "twiddle_strategy": "ROM table first; recurrence only if simpler",
                    "buffer_strategy": buffer_strategy,
                    "autontt_command": _autontt_command(task, arch, modmul),
                }
            )
    return points
