#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/evaluate_with_apptainer_and_vitis.sh --task TASK [options]

Runs the functional/Yosys evaluator inside Apptainer, then runs host
Vivado/Vitis RTL synthesis and merges the synthesis metrics into the same
results JSON.

Options:
  --task TASK          Task id from tasks/*.json, or a path to a task JSON file.
  --verilog-dir DIR   Candidate directory passed to evaluate_candidate.sh.
  --verilog-file FILE Candidate Verilog file passed to evaluate_candidate.sh.
  --build-dir DIR     Build directory. Defaults to build/eval/<task-id>.
  --results FILE      Results JSON path. Defaults to <build-dir>/results.json.
  --with-yosys        Run Yosys inside the Apptainer container.
  --sif FILE          Apptainer image. Defaults to LLM_NTT_SIF or llm-ntt.sif.
  --apptainer-bin BIN Apptainer executable. Defaults to APPTAINER_BIN or
                      apptainer.
  --vitis-part PART   FPGA part. Defaults to VITIS_PART or xcu280-fsvh2892-2L-e.
  --vitis-clock-period NS
                      Clock period in ns. Defaults to VITIS_CLOCK_PERIOD or 4.0.
  --vitis-clock-port PORT
                      Clock port. Defaults to task ports.clock, VITIS_CLOCK_PORT,
                      or clock.
  --vitis-jobs N      Vivado worker thread hint. Defaults to VITIS_JOBS or 8.
  --vitis-timeout S   Optional Vivado/Vitis timeout in seconds. Defaults to
                      VITIS_TIMEOUT or 0, meaning no timeout.
  --vivado-bin PATH   Vivado executable. Defaults to VIVADO_BIN or vivado.
  --xilinx-settings FILE
                      Source a Xilinx settings script before host synthesis.
                      Defaults to XILINX_SETTINGS, or the 2023.2 Vitis settings
                      script under /home/opt/xilinx when present.
  --no-clean          Reuse the build directory.
  -h, --help          Show this help.
EOF
}

task_arg=""
verilog_dir=""
verilog_file=""
build_dir=""
results_file=""
with_yosys=0
sif="${LLM_NTT_SIF:-${repo_root}/llm-ntt.sif}"
apptainer_bin="${APPTAINER_BIN:-apptainer}"
vitis_part="${VITIS_PART:-xcu280-fsvh2892-2L-e}"
vitis_clock_period="${VITIS_CLOCK_PERIOD:-4.0}"
vitis_clock_port="${VITIS_CLOCK_PORT:-}"
vitis_jobs="${VITIS_JOBS:-8}"
vitis_timeout="${VITIS_TIMEOUT:-0}"
vivado_bin="${VIVADO_BIN:-vivado}"
xilinx_settings="${XILINX_SETTINGS:-}"
if [[ -z "${xilinx_settings}" && -f /home/opt/xilinx/Vitis/2023.2/settings64.sh ]]; then
  xilinx_settings="/home/opt/xilinx/Vitis/2023.2/settings64.sh"
fi
clean_build=1

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
    --sif)
      sif="${2:-}"
      shift 2
      ;;
    --apptainer-bin)
      apptainer_bin="${2:-}"
      shift 2
      ;;
    --vitis-part)
      vitis_part="${2:-}"
      shift 2
      ;;
    --vitis-clock-period)
      vitis_clock_period="${2:-}"
      shift 2
      ;;
    --vitis-clock-port)
      vitis_clock_port="${2:-}"
      shift 2
      ;;
    --vitis-jobs)
      vitis_jobs="${2:-}"
      shift 2
      ;;
    --vitis-timeout)
      vitis_timeout="${2:-}"
      shift 2
      ;;
    --vivado-bin)
      vivado_bin="${2:-}"
      shift 2
      ;;
    --xilinx-settings)
      xilinx_settings="${2:-}"
      shift 2
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

if ! command -v "${apptainer_bin}" >/dev/null 2>&1; then
  echo "Apptainer executable not found: ${apptainer_bin}" >&2
  exit 127
fi

if [[ ! -f "${sif}" ]]; then
  echo "Apptainer image not found: ${sif}" >&2
  echo "Build it with: apptainer build --mksquashfs-args \"-processors 1\" llm-ntt.sif apptainer/llm-ntt.def" >&2
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

abs_path() {
  local path="$1"
  if [[ "${path}" == /* ]]; then
    readlink -m "${path}"
  else
    readlink -m "${repo_root}/${path}"
  fi
}

task_id="$(json_get id)"
top_module="$(json_get top_module)"
candidate_file="$(json_get verilog.candidate_file)"
default_path="$(json_get verilog.default_path)"

if [[ -z "${vitis_clock_port}" ]]; then
  vitis_clock_port="$(python3 - "$task_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)

print(data.get("ports", {}).get("clock", "clock"))
PY
)"
fi

if [[ -z "${build_dir}" ]]; then
  build_dir="${repo_root}/build/eval/${task_id}"
else
  build_dir="$(abs_path "${build_dir}")"
fi

if [[ -z "${results_file}" ]]; then
  results_file="${build_dir}/results.json"
else
  results_file="$(abs_path "${results_file}")"
fi

if [[ -z "${verilog_file}" ]]; then
  if [[ -n "${verilog_dir}" ]]; then
    verilog_file="${verilog_dir%/}/${candidate_file}"
  else
    verilog_file="${repo_root}/${default_path}"
  fi
fi
verilog_file="$(abs_path "${verilog_file}")"
if [[ -n "${verilog_dir}" ]]; then
  verilog_dir="$(abs_path "${verilog_dir}")"
fi

mkdir -p "$(dirname "${results_file}")" "${build_dir}"

binds=("${repo_root}:${repo_root}")
add_bind_for_path() {
  local path="$1"
  local dir
  dir="$(dirname "$(abs_path "${path}")")"
  case "${dir}" in
    "${repo_root}"|"${repo_root}"/*)
      return
      ;;
  esac
  binds+=("${dir}:${dir}")
}

add_bind_for_path "${build_dir}"
add_bind_for_path "${results_file}"
add_bind_for_path "${verilog_file}"
if [[ -n "${verilog_dir}" ]]; then
  add_bind_for_path "${verilog_dir}"
fi

apptainer_args=(exec --no-home --pwd "${repo_root}")
for bind in "${binds[@]}"; do
  apptainer_args+=(--bind "${bind}")
done
apptainer_args+=("${sif}")

eval_args=(--task "${task_file}" --verilog-file "${verilog_file}" \
  --build-dir "${build_dir}" --results "${results_file}")
if [[ "${with_yosys}" -eq 1 ]]; then
  eval_args+=(--with-yosys)
fi
if [[ "${clean_build}" -eq 0 ]]; then
  eval_args+=(--no-clean)
fi

set +e
"${apptainer_bin}" "${apptainer_args[@]}" \
  "${repo_root}/scripts/evaluate_candidate.sh" "${eval_args[@]}"
functional_status=$?
set -e

vitis_log="${build_dir}/vitis-synth.log"
vitis_json="${build_dir}/vitis-synth-metrics.json"
vitis_build_dir="${build_dir}/vitis-synth"

start_time="$(date +%s)"
set +e
"${repo_root}/scripts/vitis_synth_rtl.sh" \
  --top "${top_module}" \
  --verilog-file "${verilog_file}" \
  --build-dir "${vitis_build_dir}" \
  --metrics-json "${vitis_json}" \
  --part "${vitis_part}" \
  --clock-port "${vitis_clock_port}" \
  --clock-period "${vitis_clock_period}" \
  --jobs "${vitis_jobs}" \
  --timeout "${vitis_timeout}" \
  --vivado-bin "${vivado_bin}" \
  --xilinx-settings "${xilinx_settings}" >"${vitis_log}" 2>&1
vitis_status=$?
set -e
vitis_seconds=$(( $(date +%s) - start_time ))

python3 - "$results_file" "$vitis_json" "$vitis_log" "$vitis_status" \
  "$vitis_seconds" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

results_file, vitis_json, vitis_log, vitis_status, vitis_seconds = sys.argv[1:]

if os.path.exists(results_file):
    with open(results_file, "r", encoding="utf-8") as f:
        result = json.load(f)
else:
    result = {
        "schema": "llm-ntt-evaluation-v1",
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "correct": False,
        "metrics": {},
        "status": {},
        "seconds": {},
        "logs": {},
    }

vitis_stats = {}
if os.path.exists(vitis_json):
    with open(vitis_json, "r", encoding="utf-8") as f:
        vitis_stats = json.load(f)

vitis_passed = int(vitis_status) == 0 and bool(vitis_stats.get("passed", False))
result.setdefault("metrics", {}).update(vitis_stats.get("metrics", {}))
result.setdefault("status", {})["vitis"] = int(vitis_status)
result.setdefault("seconds", {})["vitis"] = int(vitis_seconds)
result.setdefault("logs", {})["vitis"] = os.path.relpath(vitis_log, os.getcwd())
result.setdefault("logs", {})["vitis_json"] = os.path.relpath(vitis_json, os.getcwd())
result["vitis_synthesis_passed"] = vitis_passed
result["synthesis_passed"] = bool(result.get("synthesis_passed", False)) or vitis_passed

with open(results_file, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, sort_keys=True)
    f.write("\n")

print(json.dumps(result, indent=2, sort_keys=True))
PY

exit "${functional_status}"
