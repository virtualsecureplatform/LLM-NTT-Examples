"""Prompt construction for LLM-NTT RTL candidates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def clip_middle(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    half = max(1, (limit - 80) // 2)
    return (
        text[:half]
        + "\n\n[... clipped to fit prompt budget ...]\n\n"
        + text[-half:]
    )


def read_text(path: Path, limit: int = 0) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return clip_middle(text, limit) if limit else text


def extract_module_declaration(path: Path, top_module: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"(?m)^module\s+{re.escape(top_module)}\s*\(", text)
    if not match:
        return ""
    start = match.start()
    tail = text[start:]
    lines = []
    for line in tail.splitlines():
        lines.append(line)
        if line.strip() == ");":
            break
    return "\n".join(lines)


def _test_source_path(repo_root: Path, task: dict[str, Any]) -> Path | None:
    target = task.get("evaluation", {}).get("test_target")
    if not target:
        return None
    path = repo_root / "tests" / "cpp" / f"{target}.cpp"
    if path.exists():
        return path
    return None


def build_messages(
    repo_root: Path,
    task_file: Path,
    task: dict[str, Any],
    search_point: dict[str, Any],
    feedback: str = "",
    extra_instructions: list[str] | None = None,
    spec_char_limit: int = 36000,
    include_test_source: bool = True,
) -> list[dict[str, str]]:
    top_module = str(task["top_module"])
    verilog_default = repo_root / str(task.get("verilog", {}).get("default_path", ""))
    top_decl = extract_module_declaration(verilog_default, top_module)

    docs = {
        "ntt-module-specs.md": read_text(
            repo_root / "docs" / "ntt-module-specs.md", spec_char_limit
        ),
        "architecture-search-space.md": read_text(
            repo_root / "docs" / "architecture-search-space.md", 16000
        ),
        "scoring.md": read_text(repo_root / "docs" / "scoring.md", 12000),
    }

    test_source = ""
    if include_test_source:
        test_path = _test_source_path(repo_root, task)
        if test_path is not None:
            test_source = read_text(test_path, 22000)

    instruction_text = ""
    if extra_instructions:
        instruction_text = "\n".join(f"- {item}" for item in extra_instructions)

    system = (
        "You generate Verilog/SystemVerilog RTL for LLM-NTT benchmark tasks. "
        "Return exactly one complete Verilog source file. Do not include prose "
        "outside the code block. Preserve the required top module name, port "
        "names, port widths, reset polarity, valid timing, stream order, packed "
        "lane order, modulus, and transform behavior. Do not use DPI, external "
        "include files, delays, file I/O, randomization, or testbench code."
    )

    user = f"""
Generate a candidate Verilog file for this LLM-NTT task.

Hard requirements:
- The file must define module `{top_module}`.
- The module declaration must match the task contract exactly.
- The candidate will be evaluated by `scripts/evaluate_candidate.sh`.
- Correctness is a hard gate; latency and resource metrics only matter after
  the Verilator/C++ reference test passes.
- Output one fenced code block tagged `verilog`.

Task manifest path:
{task_file}

Task manifest JSON:
```json
{json.dumps(task, indent=2, sort_keys=True)}
```

Selected AutoNTT-style search point:
```json
{json.dumps(search_point, indent=2, sort_keys=True)}
```

Normative top-level module declaration from the extracted baseline, when
available. Match this spelling and packed/unpacked shape:
```verilog
{top_decl}
```

Prime-specific implementation notes:
- For HOGE p64, `P = 0xffffffff00000001 = 2^64 - 2^32 + 1`, so
  `2^64 == 2^32 - 1 (mod P)`. A custom reducer can repeatedly fold the high
  half of a product with this relation instead of using division.
- For YATA p27, `P = 40960001 = 5^4 * 2^16 + 1`; the arithmetic is signed
  27-bit compressed RAINTT arithmetic, so normalize back into the task's
  signed modular representation before exposing outputs.

Additional user instructions:
{instruction_text or "- none"}

Previous attempt feedback:
```text
{feedback or "No previous attempt."}
```

Reference C++ test source excerpt:
```cpp
{test_source or "Not included."}
```

Specification excerpts:
```markdown
## docs/ntt-module-specs.md
{docs["ntt-module-specs.md"]}

## docs/architecture-search-space.md
{docs["architecture-search-space.md"]}

## docs/scoring.md
{docs["scoring.md"]}
```
"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_verilog(text: str) -> str:
    fence = re.search(
        r"```(?:systemverilog|verilog|sv)?\s*\n(.*?)```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence:
        return fence.group(1).strip() + "\n"
    first_module = re.search(r"(?m)^\s*module\s+\w+\b", text)
    if first_module:
        return text[first_module.start() :].strip() + "\n"
    return text.strip() + "\n"


def require_module(verilog: str, top_module: str) -> None:
    if not re.search(rf"(?m)^\s*module\s+{re.escape(top_module)}\b", verilog):
        raise ValueError(f"generated source does not define module {top_module}")
