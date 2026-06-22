#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/evaluate_behavioral_candidates.sh [options]

Generates AutoNTT-style behavioral RTL candidates and evaluates them with the
prepared task tests.

Options:
  --candidate-source SOURCE
                       Candidate source passed to autontt_llm_generate.py.
                       Defaults to "behavioral"; use "llm_behavioral" to have
                       an endpoint select the bounded functional generator.
  --endpoint ENDPOINT  Endpoint passed to autontt_llm_generate.py, for example
                       "lab" with LLM_NTT_LAB_ENDPOINT set.
  --timeout SECONDS    Chat wall-clock timeout for endpoint-backed sources.
  --max-tokens N       Completion token limit for endpoint-backed sources.
  --extra-body-json JSON
                       Extra JSON body merged into endpoint chat requests.
  --sif FILE           Apptainer image passed to autontt_llm_generate.py.
                       Defaults to the runner's auto-detection. Use "none" for
                       host evaluation.
  --apptainer-bin BIN  Apptainer executable passed to autontt_llm_generate.py.
  --with-yosys         Run optional Yosys estimates after correctness.
  --with-vitis         Run optional host Vivado/Vitis RTL synthesis after
                       correctness.
  --vitis-part PART    FPGA part for --with-vitis.
  --vitis-clock-period NS
                       Clock period in ns for --with-vitis.
  --vitis-clock-port PORT
                       Clock port for --with-vitis.
  --vitis-jobs N       Vivado worker thread hint for --with-vitis.
  --vivado-bin PATH    Vivado executable for --with-vitis.
  --xilinx-settings FILE
                       Xilinx settings script for --with-vitis.
  --task TASK          Evaluate only one supported behavioral task. May be
                       repeated.
  -h, --help           Show this help.
EOF
}

candidate_source="behavioral"
endpoint=""
timeout=""
max_tokens=""
extra_body_json=""
sif=""
apptainer_bin=""
with_yosys=0
with_vitis=0
vitis_part=""
vitis_clock_period=""
vitis_clock_port=""
vitis_jobs=""
vivado_bin=""
xilinx_settings=""
tasks=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate-source)
      candidate_source="${2:-}"
      shift 2
      ;;
    --endpoint)
      endpoint="${2:-}"
      shift 2
      ;;
    --timeout)
      timeout="${2:-}"
      shift 2
      ;;
    --max-tokens)
      max_tokens="${2:-}"
      shift 2
      ;;
    --extra-body-json)
      extra_body_json="${2:-}"
      shift 2
      ;;
    --sif)
      sif="${2:-}"
      shift 2
      ;;
    --apptainer-bin)
      apptainer_bin="${2:-}"
      shift 2
      ;;
    --with-yosys)
      with_yosys=1
      shift
      ;;
    --with-vitis)
      with_vitis=1
      shift
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
    --vivado-bin)
      vivado_bin="${2:-}"
      shift 2
      ;;
    --xilinx-settings)
      xilinx_settings="${2:-}"
      shift 2
      ;;
    --task)
      tasks+=("${2:-}")
      shift 2
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

case "${candidate_source}" in
  behavioral|llm_behavioral)
    ;;
  *)
    echo "Unsupported --candidate-source: ${candidate_source}" >&2
    exit 2
    ;;
esac

if [[ "${#tasks[@]}" -eq 0 ]]; then
  tasks=(
    hoge_streaming_intt_1024_p64
    hoge_externalproduct_ntt_1024_p64
    hoge_nttid_1024_identity
    yata_raintt_512_p27
    hoge_streaming_ntt_1024_p64
  )
fi

run_dirs=()
for task in "${tasks[@]}"; do
  arch_type="I"
  modmul_type="C"
  if [[ "${task}" == "yata_raintt_512_p27" ]]; then
    modmul_type="B"
  fi

  cmd=(
    "${repo_root}/scripts/autontt_llm_generate.py"
    --task "${task}"
    --candidate-source "${candidate_source}"
    --strategy hardware
    --arch-type "${arch_type}"
    --modmul-type "${modmul_type}"
    --attempts 1
  )
  if [[ -n "${endpoint}" ]]; then
    cmd+=(--endpoint "${endpoint}")
  fi
  if [[ -n "${timeout}" ]]; then
    cmd+=(--timeout "${timeout}")
  fi
  if [[ -n "${max_tokens}" ]]; then
    cmd+=(--max-tokens "${max_tokens}")
  fi
  if [[ -n "${extra_body_json}" ]]; then
    cmd+=(--extra-body-json "${extra_body_json}")
  fi
  if [[ "${with_yosys}" -eq 1 ]]; then
    cmd+=(--with-yosys)
  fi
  if [[ "${with_vitis}" -eq 1 ]]; then
    cmd+=(--with-vitis)
  fi
  if [[ -n "${sif}" ]]; then
    cmd+=(--sif "${sif}")
  fi
  if [[ -n "${apptainer_bin}" ]]; then
    cmd+=(--apptainer-bin "${apptainer_bin}")
  fi
  if [[ -n "${vitis_part}" ]]; then
    cmd+=(--vitis-part "${vitis_part}")
  fi
  if [[ -n "${vitis_clock_period}" ]]; then
    cmd+=(--vitis-clock-period "${vitis_clock_period}")
  fi
  if [[ -n "${vitis_clock_port}" ]]; then
    cmd+=(--vitis-clock-port "${vitis_clock_port}")
  fi
  if [[ -n "${vitis_jobs}" ]]; then
    cmd+=(--vitis-jobs "${vitis_jobs}")
  fi
  if [[ -n "${vivado_bin}" ]]; then
    cmd+=(--vivado-bin "${vivado_bin}")
  fi
  if [[ -n "${xilinx_settings}" ]]; then
    cmd+=(--xilinx-settings "${xilinx_settings}")
  fi

  echo "==> ${task}"
  output="$("${cmd[@]}")"
  printf '%s\n' "${output}"
  run_dir="$(printf '%s\n' "${output}" | awk -F': ' '/^run directory:/ {print $2}')"
  if [[ -n "${run_dir}" ]]; then
    run_dirs+=("${run_dir}")
  fi
done

python3 - "${run_dirs[@]}" <<'PY'
import json
import sys
from pathlib import Path

ok = True
for run_dir_arg in sys.argv[1:]:
    run_dir = Path(run_dir_arg)
    result_files = sorted(run_dir.glob("attempt_*/results.json"))
    for result_file in result_files:
        result = json.loads(result_file.read_text(encoding="utf-8"))
        task_id = result.get("task_id")
        correct = result.get("correct")
        build = result.get("build_passed")
        test = result.get("test_passed")
        lint = result.get("lint_passed")
        vitis = result.get("vitis_synthesis_passed")
        mode = result.get("mode")
        print(
            f"{task_id}: mode={mode} correct={correct} "
            f"build={build} test={test} lint={lint} vitis={vitis}"
        )
        if not correct:
            ok = False

if not ok:
    raise SystemExit(1)
PY
