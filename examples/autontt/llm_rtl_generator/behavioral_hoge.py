"""Deterministic structural RTL generators for HOGE tasks."""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_hoge_structural_seed(top_name: str, description: str) -> str:
    """Return checked-in staged HOGE RTL for the behavioral candidate path.

    The original Python behavioral generators were useful correctness oracles,
    but the arithmetic paths performed full polynomial transforms inside
    procedural tasks. Those are simulation models, not good hardware candidates.
    The built-in HOGE behavioral path now mirrors YATA: emit a deterministic
    structural seed from the checked-in Chisel pipeline RTL, then let the normal
    validator, Verilator tests, hardware screen, and optional Vitis run decide
    whether the candidate is acceptable. This keeps it separate from
    ``--candidate-source reference`` while making the built-in generated path
    synthesis-oriented.
    """

    rtl_path = _repo_root() / "variants" / "hoge" / "chisel" / f"{top_name}.v"
    rtl = rtl_path.read_text(encoding="utf-8")
    header = (
        f"// Generated structural HOGE {description} candidate.\n"
        "// Seeded from the checked-in Chisel pipeline RTL so the behavioral\n"
        "// candidate-source path exercises a staged synthesizable design.\n"
    )
    return header + rtl


def generate_hoge_streaming_intt_behavioral() -> str:
    """Return staged synthesizable RTL for HOGE 1024-point streaming INTT."""

    return _load_hoge_structural_seed("INTTWrap", "streaming INTT")


def generate_hoge_externalproduct_behavioral() -> str:
    """Return staged synthesizable RTL for the HOGE ExternalProduct task."""

    return _load_hoge_structural_seed("ExternalProductWrap", "ExternalProduct")


def generate_hoge_nttid_behavioral() -> str:
    """Return staged synthesizable RTL for HOGE NTT/INTT identity."""

    return _load_hoge_structural_seed("NTTidPackedTop", "NTTid identity")


def generate_hoge_streaming_ntt_interface_behavioral() -> str:
    """Return staged synthesizable RTL for the HOGE streaming NTT wrapper.

    The repository task for this top is still lint-only because no standalone
    forward-NTT oracle exists here. The emitted RTL is nevertheless the
    checked-in staged Chisel pipeline rather than a pass-through shell.
    """

    return _load_hoge_structural_seed("NTTWrap", "streaming NTT interface")
