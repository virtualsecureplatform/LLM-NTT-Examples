#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/evaluate_candidate.sh --task TASK [options]

Options:
  --task TASK          Task id from tasks/*.json, or a path to a task JSON file.
  --verilog-dir DIR   Directory containing the candidate Verilog file named by
                      the task manifest. If omitted, the baseline RTL is used.
  --verilog-file FILE Candidate Verilog file. Overrides --verilog-dir.
  --build-dir DIR     CMake build directory. Defaults to build/eval/<task-id>.
  --results FILE      Results JSON path. Defaults to <build-dir>/results.json.
  --with-yosys        Run an optional flattened Yosys resource estimate and
                      merge structural counts into the result metrics.
  --no-clean          Reuse the build directory instead of deleting it first.
  -h, --help          Show this help.
EOF
}

task_arg=""
verilog_dir=""
verilog_file=""
build_dir=""
results_file=""
clean_build=1
with_yosys=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      task_arg="${2:-}"
      shift 2
      ;;
    --verilog-dir)
      verilog_dir="${2:-}"
      shift 2
      ;;
    --verilog-file)
      verilog_file="${2:-}"
      shift 2
      ;;
    --build-dir)
      build_dir="${2:-}"
      shift 2
      ;;
    --results)
      results_file="${2:-}"
      shift 2
      ;;
    --with-yosys)
      with_yosys=1
      shift
      ;;
    --no-clean)
      clean_build=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${task_arg}" ]]; then
  echo "Missing required --task" >&2
  usage >&2
  exit 2
fi

if [[ "${task_arg}" == *.json || "${task_arg}" == */* ]]; then
  task_file="${task_arg}"
else
  task_file="${repo_root}/tasks/${task_arg}.json"
fi

if [[ ! -f "${task_file}" ]]; then
  echo "Task manifest not found: ${task_file}" >&2
  exit 2
fi

json_get() {
  local expr="$1"
  python3 - "$task_file" "$expr" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)

value = data
for part in sys.argv[2].split("."):
    value = value[part]

if value is None:
    print("")
else:
    print(value)
PY
}

task_id="$(json_get id)"
mode="$(json_get evaluation.mode)"
top_module="$(json_get top_module)"

if [[ "${mode}" == "planned" ]]; then
  echo "Task '${task_id}' is planned and is not supported by the evaluator yet." >&2
  exit 2
fi

candidate_file="$(json_get verilog.candidate_file)"
default_path="$(json_get verilog.default_path)"

if [[ -z "${verilog_file}" ]]; then
  if [[ -n "${verilog_dir}" ]]; then
    verilog_file="${verilog_dir%/}/${candidate_file}"
  else
    verilog_file="${repo_root}/${default_path}"
  fi
fi

if [[ ! -f "${verilog_file}" ]]; then
  echo "Verilog file not found: ${verilog_file}" >&2
  exit 2
fi

if [[ -z "${build_dir}" ]]; then
  build_dir="${repo_root}/build/eval/${task_id}"
fi
if [[ -z "${results_file}" ]]; then
  results_file="${build_dir}/results.json"
fi

mkdir -p "$(dirname "${results_file}")"
if [[ "${clean_build}" -eq 1 ]]; then
  rm -rf "${build_dir}"
fi
mkdir -p "${build_dir}"

configure_log="${build_dir}/configure.log"
build_log="${build_dir}/build.log"
test_log="${build_dir}/test.log"
lint_log="${build_dir}/lint.log"
yosys_log="${build_dir}/yosys.log"
yosys_json="${build_dir}/yosys-stats.json"

run_logged() {
  local log_file="$1"
  shift
  set +e
  "$@" >"${log_file}" 2>&1
  local status=$?
  set -e
  return "${status}"
}

build_passed=false
test_passed=false
lint_passed=false
configure_status=0
build_status=0
test_status=0
lint_status=0
build_seconds=0
test_seconds=0
yosys_passed=false
yosys_status=0
yosys_seconds=0

if [[ "${mode}" == "verilator_test" ]]; then
  cmake_var="$(json_get evaluation.cmake_cache_var)"
  test_target="$(json_get evaluation.test_target)"

  start_time="$(date +%s)"
  if run_logged "${configure_log}" \
      cmake -S "${repo_root}" -B "${build_dir}" -G Ninja \
        -DCMAKE_CXX_COMPILER="${CXX:-clang++}" \
        -DCMAKE_C_COMPILER="${CC:-clang}" \
        -D"${cmake_var}=${verilog_file}"; then
    configure_status=0
  else
    configure_status=$?
  fi

  if [[ "${configure_status}" -eq 0 ]] &&
     run_logged "${build_log}" cmake --build "${build_dir}" --target "${test_target}"; then
    build_status=0
    build_passed=true
  else
    build_status=$?
  fi
  build_seconds=$(( $(date +%s) - start_time ))

  start_time="$(date +%s)"
  if [[ "${build_passed}" == true ]] &&
     run_logged "${test_log}" "${build_dir}/${test_target}"; then
    test_status=0
    test_passed=true
  else
    test_status=$?
  fi
  test_seconds=$(( $(date +%s) - start_time ))

elif [[ "${mode}" == "lint_only" ]]; then
  start_time="$(date +%s)"
  if run_logged "${lint_log}" \
      verilator --lint-only -Wno-fatal --top-module "${top_module}" "${verilog_file}"; then
    lint_status=0
    lint_passed=true
  else
    lint_status=$?
  fi
  build_seconds=$(( $(date +%s) - start_time ))
else
  echo "Unsupported evaluation mode '${mode}' in ${task_file}" >&2
  exit 2
fi

if [[ "${with_yosys}" -eq 1 ]]; then
  start_time="$(date +%s)"
  yosys_script="${build_dir}/yosys.ys"
  {
    printf 'read_verilog -sv "%s"\n' "${verilog_file}"
    printf 'hierarchy -top %s\n' "${top_module}"
    printf 'proc\nopt\nmemory\nopt\nflatten\nopt\nstat -json\n'
  } >"${yosys_script}"

  if command -v yosys >/dev/null 2>&1 &&
     run_logged "${yosys_log}" yosys -Q -s "${yosys_script}"; then
    if python3 - "${yosys_log}" "${yosys_json}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

start = text.find("{\n")
end = text.rfind("\n}")
if start < 0 or end < 0:
    raise SystemExit("Yosys JSON block not found")

stats = json.loads(text[start : end + 2])
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, sort_keys=True)
    f.write("\n")
PY
    then
      yosys_status=0
      yosys_passed=true
    else
      yosys_status=$?
    fi
  else
    yosys_status=$?
  fi
  yosys_seconds=$(( $(date +%s) - start_time ))
fi

python3 - "$results_file" "$task_file" "$task_id" "$mode" "$top_module" \
  "$verilog_file" "$build_dir" "$configure_status" "$build_status" \
  "$test_status" "$lint_status" "$build_passed" "$test_passed" \
  "$lint_passed" "$build_seconds" "$test_seconds" "$configure_log" \
  "$build_log" "$test_log" "$lint_log" "$with_yosys" "$yosys_status" \
  "$yosys_passed" "$yosys_seconds" "$yosys_log" "$yosys_json" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone

(
    results_file,
    task_file,
    task_id,
    mode,
    top_module,
    verilog_file,
    build_dir,
    configure_status,
    build_status,
    test_status,
    lint_status,
    build_passed,
    test_passed,
    lint_passed,
    build_seconds,
    test_seconds,
    configure_log,
    build_log,
    test_log,
    lint_log,
    with_yosys,
    yosys_status,
    yosys_passed,
    yosys_seconds,
    yosys_log,
    yosys_json,
) = sys.argv[1:]

def as_bool(value):
    return value in ("true", "1")

def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def parse_metric_value(value):
    try:
        return int(value, 0)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value

test_output = read_text(test_log)
metrics = {}
for line in test_output.splitlines():
    if not line.startswith("METRIC "):
        continue
    payload = line[len("METRIC "):]
    if "=" not in payload:
        continue
    key, value = payload.split("=", 1)
    metrics[key.strip()] = parse_metric_value(value.strip())

def sanitize_metric_suffix(value):
    value = value.lstrip("$").lstrip("\\")
    value = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    return value.lower() or "unknown"

if as_bool(with_yosys) and as_bool(yosys_passed) and os.path.exists(yosys_json):
    with open(yosys_json, "r", encoding="utf-8") as f:
        yosys_stats = json.load(f)
    module_key = "\\" + top_module
    stats = yosys_stats.get("modules", {}).get(module_key, yosys_stats.get("design", {}))
    for key in (
        "num_wires",
        "num_wire_bits",
        "num_pub_wires",
        "num_pub_wire_bits",
        "num_ports",
        "num_port_bits",
        "num_memories",
        "num_memory_bits",
        "num_processes",
        "num_cells",
    ):
        if key in stats:
            metrics[f"yosys_{key}"] = stats[key]
    for cell_type, count in stats.get("num_cells_by_type", {}).items():
        metrics[f"yosys_cell_{sanitize_metric_suffix(cell_type)}"] = count

correct = False
if mode == "verilator_test":
    correct = as_bool(build_passed) and as_bool(test_passed)
elif mode == "lint_only":
    correct = as_bool(lint_passed)

result = {
    "schema": "llm-ntt-evaluation-v1",
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "task_id": task_id,
    "task_file": os.path.relpath(task_file, os.getcwd()),
    "mode": mode,
    "top_module": top_module,
    "verilog_file": os.path.relpath(verilog_file, os.getcwd()),
    "build_dir": os.path.relpath(build_dir, os.getcwd()),
    "correct": correct,
    "build_passed": as_bool(build_passed),
    "test_passed": as_bool(test_passed),
    "lint_passed": as_bool(lint_passed),
    "synthesis_passed": as_bool(yosys_passed) if as_bool(with_yosys) else False,
    "status": {
        "configure": int(configure_status),
        "build": int(build_status),
        "test": int(test_status),
        "lint": int(lint_status),
        "yosys": int(yosys_status),
    },
    "seconds": {
        "build": int(build_seconds),
        "test": int(test_seconds),
        "yosys": int(yosys_seconds),
    },
    "metrics": metrics,
    "logs": {
        "configure": os.path.relpath(configure_log, os.getcwd()),
        "build": os.path.relpath(build_log, os.getcwd()),
        "test": os.path.relpath(test_log, os.getcwd()),
        "lint": os.path.relpath(lint_log, os.getcwd()),
        "yosys": os.path.relpath(yosys_log, os.getcwd()),
        "yosys_json": os.path.relpath(yosys_json, os.getcwd()),
    },
}

with open(results_file, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, sort_keys=True)
    f.write("\n")

print(json.dumps(result, indent=2, sort_keys=True))
PY

if [[ "${mode}" == "verilator_test" && "${test_passed}" != true ]]; then
  exit 1
fi
if [[ "${mode}" == "lint_only" && "${lint_passed}" != true ]]; then
  exit 1
fi
