#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_autontt_kunashiri_harness.sh [options]

Runs the endpoint-backed AutoNTT-style RTL-generation harness with defaults
that are known to work against the kunashiri llama.cpp OpenAI-compatible API.
Generated RTL, LLM responses, prompts, evaluator logs, and results are written
under the selected output root.

Options:
  --task TASK          Evaluate one supported task. May be repeated. Defaults
                       to all current behavioral harness tasks.
  --endpoint ENDPOINT  OpenAI-compatible endpoint alias or URL. Default:
                       kunashiri.
  --output-root ROOT   Output root for generated run artifacts. Default:
                       build/autontt-kunashiri-harness.
  --summary-file FILE  Aggregate JSON summary path. Defaults to
                       OUTPUT_ROOT/summary.json.
  --timeout SECONDS    Chat wall-clock timeout. Default: 60.
  --max-tokens N       Completion token limit for bounded JSON selection.
                       Default: 256.
  --sif FILE           Apptainer image. Default: auto. Use "none" for host
                       evaluation.
  --disable-thinking   Force chat_template_kwargs.enable_thinking=false.
                       Enabled by default for kunashiri.
  --no-disable-thinking
                       Do not add the llama.cpp/Qwen thinking override.
  --extra-body-json JSON
                       Extra JSON body merged into endpoint chat requests.
  --with-yosys         Run optional Yosys estimates after correctness.
  --with-vitis         Run optional host Vivado/Vitis synthesis after
                       correctness.
  --vitis-timeout SEC  Timeout for each Vivado/Vitis synthesis run.
  --vitis-part PART    FPGA part for --with-vitis.
  --vitis-clock-period NS
                       Clock period in ns for --with-vitis.
  --vitis-clock-port PORT
                       Clock port for --with-vitis.
  --vitis-jobs N       Vivado worker thread hint for --with-vitis.
  --vivado-bin PATH    Vivado executable for --with-vitis.
  --xilinx-settings FILE
                       Xilinx settings script for --with-vitis.
  -h, --help           Show this help.
EOF
}

endpoint="${LLM_NTT_HARNESS_ENDPOINT:-kunashiri}"
output_root="${LLM_NTT_HARNESS_OUTPUT_ROOT:-build/autontt-kunashiri-harness}"
timeout="${LLM_NTT_HARNESS_TIMEOUT:-60}"
max_tokens="${LLM_NTT_HARNESS_MAX_TOKENS:-256}"
sif="${LLM_NTT_HARNESS_SIF:-auto}"
disable_thinking=1
pass_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      pass_args+=(--task "${2:-}")
      shift 2
      ;;
    --endpoint)
      endpoint="${2:-}"
      shift 2
      ;;
    --output-root)
      output_root="${2:-}"
      shift 2
      ;;
    --summary-file)
      pass_args+=(--summary-file "${2:-}")
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
    --sif)
      sif="${2:-}"
      shift 2
      ;;
    --disable-thinking)
      disable_thinking=1
      shift
      ;;
    --no-disable-thinking)
      disable_thinking=0
      shift
      ;;
    --extra-body-json)
      pass_args+=(--extra-body-json "${2:-}")
      shift 2
      ;;
    --with-yosys|--with-vitis)
      pass_args+=("$1")
      shift
      ;;
    --vitis-timeout|--vitis-part|--vitis-clock-period|--vitis-clock-port|--vitis-jobs|--vivado-bin|--xilinx-settings)
      pass_args+=("$1" "${2:-}")
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

cmd=(
  "${repo_root}/scripts/evaluate_behavioral_candidates.sh"
  --candidate-source llm_behavioral
  --endpoint "${endpoint}"
  --output-root "${output_root}"
  --timeout "${timeout}"
  --max-tokens "${max_tokens}"
  --sif "${sif}"
)

if [[ "${disable_thinking}" -eq 1 ]]; then
  cmd+=(--disable-thinking)
fi

cmd+=("${pass_args[@]}")

printf 'Running AutoNTT-style kunashiri harness:\n'
printf '  endpoint: %s\n' "${endpoint}"
printf '  output-root: %s\n' "${output_root}"
printf '  evaluator image: %s\n' "${sif}"

exec "${cmd[@]}"
