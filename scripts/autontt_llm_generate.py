#!/usr/bin/env python3
"""Repository-local entry point for the AutoNTT-style LLM RTL generator."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from examples.autontt.llm_rtl_generator.runner import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
