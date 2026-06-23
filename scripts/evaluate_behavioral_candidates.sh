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
  --output-root ROOT   Output root passed to autontt_llm_generate.py.
  --summary-file FILE  Optional aggregate JSON summary path. If omitted and
                       --output-root is set, writes ROOT/summary.json.
  --extra-body-json JSON
                       Extra JSON body merged into endpoint chat requests.
  --disable-thinking   Pass chat_template_kwargs.enable_thinking=false to
                       llama.cpp/Qwen-style endpoint requests.
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
  --vitis-timeout SEC  Timeout passed to each Vivado/Vitis synthesis run.
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
output_root=""
summary_file=""
extra_body_json=""
disable_thinking=0
sif=""
apptainer_bin=""
with_yosys=0
with_vitis=0
vitis_part=""
vitis_clock_period=""
vitis_clock_port=""
vitis_jobs=""
vitis_timeout=""
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
    --output-root)
      output_root="${2:-}"
      shift 2
      ;;
    --summary-file)
      summary_file="${2:-}"
      shift 2
      ;;
    --extra-body-json)
      extra_body_json="${2:-}"
      shift 2
      ;;
    --disable-thinking)
      disable_thinking=1
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

if [[ -z "${summary_file}" && -n "${output_root}" ]]; then
  summary_file="${output_root%/}/summary.json"
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
  if [[ -n "${output_root}" ]]; then
    cmd+=(--output-root "${output_root}")
  fi
  if [[ -n "${extra_body_json}" ]]; then
    cmd+=(--extra-body-json "${extra_body_json}")
  fi
  if [[ "${disable_thinking}" -eq 1 ]]; then
    cmd+=(--disable-thinking)
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
  if [[ -n "${vitis_timeout}" ]]; then
    cmd+=(--vitis-timeout "${vitis_timeout}")
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

python3 - "${repo_root}" "${summary_file}" "${with_vitis}" "${tasks[@]}" -- "${run_dirs[@]}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(sys.argv[1])
summary_arg = sys.argv[2]
require_vitis = sys.argv[3] == "1"
separator = sys.argv.index("--")
task_ids = sys.argv[4:separator]
run_dir_args = sys.argv[separator + 1 :]

ok = True
results = []
if not run_dir_args:
    ok = False

for run_dir_arg in run_dir_args:
    run_dir = Path(run_dir_arg)
    result_files = sorted(run_dir.glob("attempt_*/results.json"))
    if not result_files:
        print(f"{run_dir}: no results.json files found")
        ok = False
    for result_file in result_files:
        result = json.loads(result_file.read_text(encoding="utf-8"))
        task_id = result.get("task_id")
        correct = result.get("correct")
        build = result.get("build_passed")
        test = result.get("test_passed")
        lint = result.get("lint_passed")
        vitis = result.get("vitis_synthesis_passed")
        mode = result.get("mode")
        task_ok = bool(correct)
        if require_vitis:
            task_ok = task_ok and bool(vitis)
        print(
            f"{task_id}: mode={mode} correct={correct} "
            f"build={build} test={test} lint={lint} vitis={vitis}"
        )
        if not task_ok:
            ok = False
        results.append(
            {
                "task_id": task_id,
                "mode": mode,
                "correct": correct,
                "build_passed": build,
                "test_passed": test,
                "lint_passed": lint,
                "vitis_synthesis_passed": vitis,
                "ok": task_ok,
                "run_dir": str(run_dir),
                "results_json": str(result_file),
                "candidate_source": result.get("candidate_source"),
                "metrics": result.get("metrics", {}),
            }
        )

summary = {
    "schema": "llm-ntt-behavioral-batch-summary-v1",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ok": ok,
    "require_vitis": require_vitis,
    "tasks": task_ids,
    "results": results,
}

if summary_arg:
    summary_path = Path(summary_arg)
    if not summary_path.is_absolute():
        summary_path = repo_root / summary_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"summary: {summary_path}")

if not ok:
    raise SystemExit(1)
PY
