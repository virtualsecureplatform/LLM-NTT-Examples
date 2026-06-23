#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_autontt_hls_sif_compare.sh [options]

Runs the generated AutoNTT HLS artifact through the Apptainer SIF dependency
check, C-simulation compile, and optional TAPA synthesis, then writes a summary
and report. This is the post-SIF step for deciding whether the generated HLS is
synthesizable in the current environment.

Options:
  --sif FILE           Apptainer image. Defaults to LLM_NTT_SIF, ./llm-ntt.sif,
                       or ../llm-ntt.sif.
  --hls-dir DIR        Generated AutoNTT HLS design directory. Defaults to the
                       newest HOGE custom-reduction AutoNTT artifact under
                       build/.
  --output-root DIR    Output root. Defaults to build/autontt-hls-sif-compare.
  --platform NAME      Vitis platform passed to C-sim and TAPA compile.
                       Defaults to xilinx_u200_gen3x16_xdma_2_202110_1.
  --xilinx-root DIR    Xilinx root to bind. Defaults to /home/opt/xilinx.
  --tapa-home DIR      TAPA/Pasta runtime prefix to bind and expose inside the
                       container, for example /opt/pasta or
                       /opt/rapidstream-tapa.
  --bind SRC:DST       Extra Apptainer bind. May be repeated.
  --apptainer-bin BIN  Apptainer executable. Defaults to APPTAINER_BIN or
                       apptainer.
  --skip-tapa-compile Run dependency check and csim compile only.
  --skip-tapac        Legacy alias for --skip-tapa-compile.
  --check-only         Run only scripts/check_autontt_hls_deps.sh in the SIF.
  --tapa-timeout SEC   Timeout for TAPA compile. Defaults to 3600.
  -h, --help           Show this help.
EOF
}

timestamp() {
  date -u +"%Y%m%dT%H%M%SZ"
}

rel_to_repo() {
  python3 - "$1" "$repo_root" <<'PY'
import os
import sys

print(os.path.relpath(os.path.realpath(sys.argv[1]), os.path.realpath(sys.argv[2])))
PY
}

latest_hls_artifact() {
  find "${repo_root}/build" \
    -path '*artifacts/AutoNTT_*__red_CUSTOM_REDUCTION__*' \
    -type d 2>/dev/null |
    sort |
    tail -n 1
}

sif="${LLM_NTT_SIF:-}"
if [[ -z "${sif}" ]]; then
  if [[ -f "${repo_root}/llm-ntt.sif" ]]; then
    sif="${repo_root}/llm-ntt.sif"
  elif [[ -f "${repo_root}/../llm-ntt.sif" ]]; then
    sif="${repo_root}/../llm-ntt.sif"
  else
    sif="${repo_root}/llm-ntt.sif"
  fi
fi
hls_dir=""
output_root="${repo_root}/build/autontt-hls-sif-compare"
platform="xilinx_u200_gen3x16_xdma_2_202110_1"
xilinx_root="/home/opt/xilinx"
tapa_home=""
apptainer_bin="${APPTAINER_BIN:-apptainer}"
skip_tapac=0
check_only=0
tapa_timeout="3600"
declare -a extra_binds=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sif)
      sif="${2:-}"
      shift 2
      ;;
    --hls-dir)
      hls_dir="${2:-}"
      shift 2
      ;;
    --output-root)
      output_root="${2:-}"
      shift 2
      ;;
    --platform)
      platform="${2:-}"
      shift 2
      ;;
    --xilinx-root)
      xilinx_root="${2:-}"
      shift 2
      ;;
    --tapa-home)
      tapa_home="${2:-}"
      shift 2
      ;;
    --bind)
      extra_binds+=("${2:-}")
      shift 2
      ;;
    --apptainer-bin)
      apptainer_bin="${2:-}"
      shift 2
      ;;
    --skip-tapac|--skip-tapa-compile)
      skip_tapac=1
      shift
      ;;
    --check-only)
      check_only=1
      shift
      ;;
    --tapa-timeout)
      tapa_timeout="${2:-}"
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

if [[ -z "${hls_dir}" ]]; then
  hls_dir="$(latest_hls_artifact)"
fi
if [[ -z "${hls_dir}" || ! -d "${hls_dir}" ]]; then
  echo "Generated HLS artifact not found. Pass --hls-dir." >&2
  exit 2
fi
if [[ ! -f "${sif}" ]]; then
  echo "Apptainer image not found: ${sif}" >&2
  echo "Build it with: scripts/build_llm_ntt_sif.sh --sudo" >&2
  exit 2
fi
if ! command -v "${apptainer_bin}" >/dev/null 2>&1; then
  echo "Apptainer executable not found: ${apptainer_bin}" >&2
  exit 127
fi
if ! [[ "${tapa_timeout}" =~ ^[0-9]+$ ]]; then
  echo "Invalid --tapa-timeout value: ${tapa_timeout}" >&2
  exit 2
fi

run_root="${output_root}/$(timestamp)"
work_hls="${run_root}/hls/$(basename "${hls_dir}")"
mkdir -p "${run_root}/logs" "$(dirname "${work_hls}")"
cp -a "${hls_dir}" "${work_hls}"

work_hls_rel="$(rel_to_repo "${work_hls}")"
summary_json="${run_root}/summary.json"
report_md="${run_root}/report.md"
dep_log="${run_root}/logs/dependency-check.log"
csim_log="${run_root}/logs/csim-compile.log"
tapac_log="${run_root}/logs/tapa-compile.log"

declare -a apptainer_base=(
  "${apptainer_bin}" exec
  --no-home
  --pwd /work
  --bind "${repo_root}:/work"
)
if [[ -d "${xilinx_root}" ]]; then
  apptainer_base+=(--bind "${xilinx_root}:${xilinx_root}")
fi
if [[ -d /opt/xilinx ]]; then
  apptainer_base+=(--bind /opt/xilinx:/opt/xilinx)
fi
if [[ -n "${tapa_home}" ]]; then
  apptainer_base+=(--bind "${tapa_home}:${tapa_home}")
else
  for candidate in /opt/pasta /opt/tapa /opt/rapidstream-tapa; do
    if [[ -d "${candidate}" ]]; then
      tapa_home="${candidate}"
      apptainer_base+=(--bind "${candidate}:${candidate}")
      break
    fi
  done
fi
for bind_arg in "${extra_binds[@]}"; do
  apptainer_base+=(--bind "${bind_arg}")
done
apptainer_base+=("${sif}")

container_env='
set -euo pipefail
if [[ -f /home/opt/xilinx/Vitis/2023.2/settings64.sh ]]; then
  set +u
  source /home/opt/xilinx/Vitis/2023.2/settings64.sh
  set -u
fi
export XILINX_HLS="${XILINX_HLS:-/home/opt/xilinx/Vitis_HLS/2023.2}"
for prefix in "${TAPA_HOME:-}" /opt/pasta /opt/tapa /opt/rapidstream-tapa /usr/local; do
  if [[ -n "${prefix}" && -d "${prefix}" ]]; then
    export PATH="${prefix}/usr/bin:${prefix}/bin:${PATH}"
    export CPLUS_INCLUDE_PATH="${prefix}/usr/include:${prefix}/include:${CPLUS_INCLUDE_PATH:-}"
    export LIBRARY_PATH="${prefix}/usr/lib:${prefix}/usr/lib64:${prefix}/lib:${prefix}/lib64:${LIBRARY_PATH:-}"
    export LD_LIBRARY_PATH="${prefix}/usr/lib:${prefix}/usr/lib64:${prefix}/lib:${prefix}/lib64:${LD_LIBRARY_PATH:-}"
  fi
done
for prefix in /home/opt/xilinx/xrt /opt/xilinx/xrt; do
  if [[ -d "${prefix}" ]]; then
    export CPLUS_INCLUDE_PATH="${prefix}/include:${CPLUS_INCLUDE_PATH:-}"
    export LIBRARY_PATH="${prefix}/lib:${prefix}/lib64:${LIBRARY_PATH:-}"
    export LD_LIBRARY_PATH="${prefix}/lib:${prefix}/lib64:${LD_LIBRARY_PATH:-}"
    break
  fi
done
'
if [[ -n "${tapa_home}" ]]; then
  container_env="export TAPA_HOME='${tapa_home}'; ${container_env}"
fi

run_in_sif() {
  local log_file="$1"
  local timeout_seconds="$2"
  local script="$3"
  set +e
  if [[ "${timeout_seconds}" == "0" ]]; then
    "${apptainer_base[@]}" bash -lc "${container_env}
${script}" >"${log_file}" 2>&1
  else
    timeout "${timeout_seconds}" "${apptainer_base[@]}" bash -lc "${container_env}
${script}" >"${log_file}" 2>&1
  fi
  local status=$?
  return "${status}"
}

tapa_runtime_libs="-ltapa -lfrt -lglog -lgflags -lOpenCL -lyaml-cpp -ltinyxml2 -lthread -lcontext -pthread"
patch_csim_link_line="python3 -c \"from pathlib import Path; p = Path('Makefile'); s = p.read_text(); p.write_text(s.replace('-ltapa -lfrt -lglog -lgflags -lOpenCL', '${tapa_runtime_libs}'))\""

dep_status=0
csim_status=0
tapac_status=0

set +e
run_in_sif "${dep_log}" 0 "cd /work && scripts/check_autontt_hls_deps.sh"
dep_status=$?
set -e

if [[ "${check_only}" -eq 0 ]]; then
  set +e
  run_in_sif "${csim_log}" 0 "cd '/work/${work_hls_rel}' && ${patch_csim_link_line} && make csim_compile XILINX_HLS=\"\${XILINX_HLS}\" platform='${platform}'"
  csim_status=$?
  set -e

  if [[ "${skip_tapac}" -eq 0 ]]; then
    set +e
    run_in_sif "${tapac_log}" "${tapa_timeout}" "cd '/work/${work_hls_rel}' && rm -rf 'NTT_kernel.${platform}.hw.xo.tapa' 'NTT_kernel.${platform}.hw.xo' 'NTT_kernel.${platform}.hw_generate_bitstream.sh' && tapa --work-dir='NTT_kernel.${platform}.hw.xo.tapa' compile --input=ntt_kernel.cpp --top=NTT_kernel --platform='${platform}' --clock-period=4 --output='NTT_kernel.${platform}.hw.xo' --bitstream-script='NTT_kernel.${platform}.hw_generate_bitstream.sh'"
    tapac_status=$?
    set -e
  fi
fi

python3 - \
  "${summary_json}" \
  "${report_md}" \
  "${repo_root}" \
  "${run_root}" \
  "${hls_dir}" \
  "${work_hls}" \
  "${sif}" \
  "${platform}" \
  "${dep_status}" \
  "${csim_status}" \
  "${tapac_status}" \
  "${check_only}" \
  "${skip_tapac}" \
  "${dep_log}" \
  "${csim_log}" \
  "${tapac_log}" <<'PY'
import json
import os
import sys
from pathlib import Path

(
    summary_json,
    report_md,
    repo_root,
    run_root,
    hls_dir,
    work_hls,
    sif,
    platform,
    dep_status,
    csim_status,
    tapac_status,
    check_only,
    skip_tapac,
    dep_log,
    csim_log,
    tapac_log,
) = sys.argv[1:]

repo = Path(repo_root)
run = Path(run_root)

def rel(path: str | Path) -> str:
    return os.path.relpath(Path(path).resolve(), repo.resolve())

def tail(path: str, lines: int = 25) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return data[-lines:]

def maybe_load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

prior = maybe_load_json(repo / "build/autontt-hls-compare/summary.json")
tapa_status_value = None if check_only == "1" or skip_tapac == "1" else int(tapac_status)
status = {
    "dependency_check": int(dep_status),
    "csim_compile": None if check_only == "1" else int(csim_status),
    "tapa_compile": tapa_status_value,
    "tapa_wo_floorplan": tapa_status_value,
}

full_tapac_requested = check_only == "0" and skip_tapac == "0"
synthesizable = (
    full_tapac_requested
    and int(dep_status) == 0
    and int(csim_status) == 0
    and int(tapac_status) == 0
)

if check_only == "1":
    synthesis_status = "dependency_check_only"
elif int(dep_status) != 0:
    synthesis_status = "dependency_check_failed"
elif int(csim_status) != 0:
    synthesis_status = "csim_compile_failed"
elif skip_tapac == "1":
    synthesis_status = "csim_compile_passed_tapa_compile_skipped"
elif int(tapac_status) != 0:
    synthesis_status = "tapa_compile_failed_or_timed_out"
else:
    synthesis_status = "hls_compile_and_tapa_compile_passed"

xo_files = sorted(str(p) for p in Path(work_hls).glob("NTT_kernel.*.hw.xo"))
tapa_dirs = sorted(str(p) for p in Path(work_hls).glob("NTT_kernel.*.hw.xo.tapa") if p.is_dir())

summary = {
    "schema": "llm-ntt-autontt-hls-sif-compare-v1",
    "synthesis_status": synthesis_status,
    "synthesizable": synthesizable,
    "status_codes": status,
    "sif": str(Path(sif)),
    "platform": platform,
    "source_hls_artifact": str(Path(hls_dir)),
    "work_hls_artifact": rel(work_hls),
    "logs": {
        "dependency_check": rel(dep_log),
        "csim_compile": rel(csim_log),
        "tapa_compile": rel(tapac_log),
        "tapa_wo_floorplan": rel(tapac_log),
    },
    "outputs": {
        "xo_files": [rel(path) for path in xo_files],
        "tapa_work_dirs": [rel(path) for path in tapa_dirs],
    },
    "estimate_comparisons": prior.get("comparisons", {}),
    "hls_estimates": prior.get("hls_estimates", {}),
    "tails": {
        "dependency_check": tail(dep_log),
        "csim_compile": tail(csim_log),
        "tapa_compile": tail(tapac_log),
        "tapa_wo_floorplan": tail(tapac_log),
    },
}

Path(summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

lines = [
    "# AutoNTT HLS SIF Compare",
    "",
    f"Status: `{synthesis_status}`",
    f"Synthesizable: `{'true' if synthesizable else 'false'}`",
    "",
    f"- SIF: `{sif}`",
    f"- Source HLS artifact: `{hls_dir}`",
    f"- Working HLS artifact: `{rel(work_hls)}`",
    f"- Platform: `{platform}`",
    "",
    "## Command Status",
    "",
    f"- dependency check: `{dep_status}`",
    f"- csim compile: `{'skipped' if check_only == '1' else csim_status}`",
    f"- tapa compile: `{'skipped' if check_only == '1' or skip_tapac == '1' else tapac_status}`",
    "",
]
if prior.get("hls_estimates"):
    est = prior["hls_estimates"]
    lines += [
        "## AutoNTT Estimate Baseline",
        "",
        f"- estimated cycles at 250 MHz: `{est.get('cycles_at_250mhz')}`",
        f"- LUT: `{est.get('lut')}`",
        f"- FF: `{est.get('ff')}`",
        f"- DSP: `{est.get('dsp')}`",
        f"- BRAM tile: `{est.get('bram_tile')}`",
        f"- URAM: `{est.get('uram')}`",
        "",
    ]
if prior.get("comparisons"):
    lines += ["## Existing Estimate Comparisons", ""]
    for task, item in sorted(prior["comparisons"].items()):
        lines += [
            f"### `{task}`",
            "",
            f"- reference total cycles: `{item.get('reference_total_cycles')}`",
            f"- HLS estimated cycles: `{item.get('hls_estimated_cycles')}`",
            f"- latency score reference/HLS: `{item.get('latency_score_reference_over_hls')}`",
            f"- resource penalty: `{item.get('resource_penalty')}`",
            f"- resource-aware score: `{item.get('resource_aware_score')}`",
            "",
        ]
lines += [
    "## Logs",
    "",
    f"- dependency check: `{rel(dep_log)}`",
    f"- csim compile: `{rel(csim_log)}`",
    f"- tapa compile: `{rel(tapac_log)}`",
    "",
]
Path(report_md).write_text("\n".join(lines), encoding="utf-8")
PY

echo "Summary: ${summary_json}"
echo "Report:  ${report_md}"
exit 0
