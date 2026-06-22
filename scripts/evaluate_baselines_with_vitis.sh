#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/evaluate_baselines_with_vitis.sh [options]

Generates the checked-in golden RTL inside Apptainer, evaluates every task, runs
host Vivado/Vitis RTL synthesis, and writes refreshed reference JSON files under
baselines/extracted-rtl/.

Options:
  --sif FILE          Apptainer image. Defaults to LLM_NTT_SIF or llm-ntt.sif.
  --apptainer-bin BIN Apptainer executable. Defaults to APPTAINER_BIN or
                      apptainer.
  --no-yosys         Skip Yosys structural estimates inside Apptainer.
  --skip-gen-verilog Do not run scripts/gen_verilog.sh before evaluation.
  --vitis-part PART  FPGA part. Defaults to VITIS_PART or xcu280-fsvh2892-2L-e.
  --vitis-clock-period NS
                     Clock period in ns. Defaults to VITIS_CLOCK_PERIOD or 4.0.
  --vitis-jobs N     Vivado worker thread hint. Defaults to VITIS_JOBS or 8.
  --vivado-bin PATH  Vivado executable. Defaults to VIVADO_BIN or vivado.
  --xilinx-settings FILE
                     Source a Xilinx settings script before host synthesis.
                     Defaults to XILINX_SETTINGS, or the 2023.2 Vitis settings
                     script under /home/opt/xilinx when present.
  -h, --help         Show this help.
EOF
}

sif="${LLM_NTT_SIF:-${repo_root}/llm-ntt.sif}"
apptainer_bin="${APPTAINER_BIN:-apptainer}"
with_yosys=1
gen_verilog=1
vitis_part="${VITIS_PART:-xcu280-fsvh2892-2L-e}"
vitis_clock_period="${VITIS_CLOCK_PERIOD:-4.0}"
vitis_jobs="${VITIS_JOBS:-8}"
vivado_bin="${VIVADO_BIN:-vivado}"
xilinx_settings="${XILINX_SETTINGS:-}"
if [[ -z "${xilinx_settings}" && -f /home/opt/xilinx/Vitis/2023.2/settings64.sh ]]; then
  xilinx_settings="/home/opt/xilinx/Vitis/2023.2/settings64.sh"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sif)
      sif="${2:-}"
      shift 2
      ;;
    --apptainer-bin)
      apptainer_bin="${2:-}"
      shift 2
      ;;
    --no-yosys)
      with_yosys=0
      shift
      ;;
    --skip-gen-verilog)
      gen_verilog=0
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

if ! command -v "${apptainer_bin}" >/dev/null 2>&1; then
  echo "Apptainer executable not found: ${apptainer_bin}" >&2
  exit 127
fi

if [[ ! -f "${sif}" ]]; then
  echo "Apptainer image not found: ${sif}" >&2
  echo "Build it with: apptainer build --mksquashfs-args \"-processors 1\" llm-ntt.sif apptainer/llm-ntt.def" >&2
  exit 2
fi

if [[ "${gen_verilog}" -eq 1 ]]; then
  "${apptainer_bin}" exec --no-home --pwd "${repo_root}" \
    --bind "${repo_root}:${repo_root}" \
    "${sif}" "${repo_root}/scripts/gen_verilog.sh"
fi

tasks=(
  yata_raintt_512_p27
  hoge_streaming_intt_1024_p64
  hoge_externalproduct_ntt_1024_p64
  hoge_nttid_1024_identity
  hoge_streaming_ntt_1024_p64
)

for task in "${tasks[@]}"; do
  args=(
    --task "${task}"
    --results "${repo_root}/baselines/extracted-rtl/${task}.json"
    --sif "${sif}"
    --apptainer-bin "${apptainer_bin}"
    --vitis-part "${vitis_part}"
    --vitis-clock-period "${vitis_clock_period}"
    --vitis-jobs "${vitis_jobs}"
    --vivado-bin "${vivado_bin}"
    --xilinx-settings "${xilinx_settings}"
  )
  if [[ "${with_yosys}" -eq 1 ]]; then
    args+=(--with-yosys)
  fi
  "${repo_root}/scripts/evaluate_with_apptainer_and_vitis.sh" "${args[@]}"
done
