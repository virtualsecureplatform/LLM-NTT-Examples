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
        "Return exactly one complete Verilog source file. Do not include prose, "
        "analysis, reasoning, design notes, or explanations outside the code "
        "block. Preserve the required top module name, port "
        "names, port widths, reset polarity, valid timing, stream order, packed "
        "lane order, modulus, and transform behavior. Do not use DPI, external "
        "include files, delays, file I/O, randomization, or testbench code. "
        "For non-identity tasks, implement the requested NTT/INTT arithmetic; "
        "do not return pass-through, constant-output, or test-vector-only RTL. "
        "Return complete compilable RTL, not pseudocode, ellipses, or omitted "
        "sections."
    )

    user = f"""
Generate a candidate Verilog file for this LLM-NTT task.

Hard requirements:
- The file must define module `{top_module}`.
- The module declaration must match the task contract exactly.
- The module declaration must list every port explicitly. Do not abbreviate
  repeated lanes with `..`, `...`, ranges in names, comments, prose, or omitted
  ports.
- The candidate will be evaluated by `scripts/evaluate_candidate.sh`.
- Correctness is a hard gate; latency and resource metrics only matter after
  the Verilator/C++ reference test passes.
- For real arithmetic tasks, a trivial pass-through or constant-output module is
  not acceptable even if it has the right ports. Implement the observable NTT,
  INTT, or ExternalProduct behavior described by the manifest and tests.
- The file must be complete compilable Verilog. Do not use comments such as
  "rest of code", ellipses, TODO placeholders, or omitted sections.
- Output one fenced code block tagged `verilog`.
- Output no text before or after the fenced Verilog code block.

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
- For Verilog buffers in HOGE tasks, avoid the identifier `buf`; it is a
  Verilog primitive keyword in common tools. Use names such as `coeff_mem`.
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
    match = re.search(rf"(?m)^\s*module\s+{re.escape(top_module)}\b", verilog)
    if not match:
        raise ValueError(f"generated source does not define module {top_module}")
    if not re.search(r"\bendmodule\b", verilog[match.end() :]):
        raise ValueError(f"generated source does not close module {top_module}")


def _allows_passthrough(task: dict[str, Any]) -> bool:
    task_id = str(task.get("id", "")).lower()
    if "identity" in task_id:
        return True
    reference = task.get("reference", {})
    operation = str(reference.get("operation", "")).lower()
    return "identity" in operation


def _is_lint_only(task: dict[str, Any]) -> bool:
    return str(task.get("evaluation", {}).get("mode", "")) == "lint_only"


def validate_candidate(
    verilog: str,
    task: dict[str, Any],
    allow_shortcuts: bool = False,
) -> None:
    lowered = verilog.lower()
    placeholder_patterns = [
        r"\.\.\.",
        r"rest of (?:the )?code",
        r"remaining code",
        r"omitted",
        r"todo",
        r"not shown",
    ]
    for pattern in placeholder_patterns:
        if re.search(pattern, lowered):
            raise ValueError(
                "generated source contains placeholder text instead of complete RTL"
            )
    top_module = str(task["top_module"])
    require_module(verilog, top_module)
    if allow_shortcuts or _allows_passthrough(task) or _is_lint_only(task):
        return

    compact = re.sub(r"\s+", "", verilog).lower()
    if "assignio_out=io_in;" in compact:
        raise ValueError(
            "generated source is a direct io_out=io_in pass-through for a "
            "non-identity arithmetic task"
        )

    nonblank_lines = [line for line in verilog.splitlines() if line.strip()]
    params = task.get("parameters", {})
    problem_size = int(params.get("N", 0) or 0)
    if problem_size >= 512 and len(nonblank_lines) < 32:
        raise ValueError(
            "generated source is too small for a nontrivial arithmetic task; "
            "use --allow-shortcuts only for explicit smoke testing"
        )
