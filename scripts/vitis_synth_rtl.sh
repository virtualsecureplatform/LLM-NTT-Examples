#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/vitis_synth_rtl.sh --top TOP --verilog-file FILE [--verilog-file FILE ...] [options]

Options:
  --top TOP              Top Verilog module to synthesize.
  --verilog-file FILE    Verilog source file. Repeat for multi-file RTL.
  --build-dir DIR        Output directory. Defaults to build/vitis-synth/<top>.
  --metrics-json FILE    Parsed metrics JSON path. Defaults to
                         <build-dir>/vitis-synth-metrics.json.
  --part PART            FPGA part. Defaults to VITIS_PART or the AutoNTT U280
                         part xcu280-fsvh2892-2L-e.
  --clock-port PORT      Clock port to constrain. Defaults to VITIS_CLOCK_PORT
                         or clock.
  --clock-period NS      Clock period in ns. Defaults to VITIS_CLOCK_PERIOD or
                         4.0, matching AutoNTT examples.
  --jobs N               Vivado worker thread hint. Defaults to VITIS_JOBS or 8.
  --timeout S            Optional Vivado timeout in seconds. Defaults to
                         VITIS_TIMEOUT or 0, meaning no timeout.
  --vivado-bin PATH      Vivado executable. Defaults to VIVADO_BIN or vivado.
  --xilinx-settings FILE Source a Xilinx settings script before running Vivado.
                         Defaults to XILINX_SETTINGS, or
                         /home/opt/xilinx/Vitis/2023.2/settings64.sh when it
                         exists.
  --no-clean             Reuse the output directory.
  -h, --help             Show this help.
EOF
}

top_module=""
verilog_files=()
build_dir=""
metrics_json=""
part="${VITIS_PART:-xcu280-fsvh2892-2L-e}"
clock_port="${VITIS_CLOCK_PORT:-clock}"
clock_period="${VITIS_CLOCK_PERIOD:-4.0}"
jobs="${VITIS_JOBS:-8}"
timeout_seconds="${VITIS_TIMEOUT:-0}"
vivado_bin="${VIVADO_BIN:-vivado}"
xilinx_settings="${XILINX_SETTINGS:-}"
if [[ -z "${xilinx_settings}" && -f /home/opt/xilinx/Vitis/2023.2/settings64.sh ]]; then
  xilinx_settings="/home/opt/xilinx/Vitis/2023.2/settings64.sh"
fi
clean_build=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --top)
      top_module="${2:-}"
      shift 2
      ;;
    --verilog-file)
      verilog_files+=("${2:-}")
      shift 2
      ;;
    --build-dir)
      build_dir="${2:-}"
      shift 2
      ;;
    --metrics-json)
      metrics_json="${2:-}"
      shift 2
      ;;
    --part)
      part="${2:-}"
      shift 2
      ;;
    --clock-port)
      clock_port="${2:-}"
      shift 2
      ;;
    --clock-period)
      clock_period="${2:-}"
      shift 2
      ;;
    --jobs)
      jobs="${2:-}"
      shift 2
      ;;
    --timeout|--vitis-timeout)
      timeout_seconds="${2:-}"
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

if [[ -z "${top_module}" || "${#verilog_files[@]}" -eq 0 ]]; then
  echo "Missing required --top or --verilog-file" >&2
  usage >&2
  exit 2
fi

if ! [[ "${timeout_seconds}" =~ ^[0-9]+$ ]]; then
  echo "Invalid --timeout value: ${timeout_seconds}" >&2
  exit 2
fi

for i in "${!verilog_files[@]}"; do
  if [[ ! -f "${verilog_files[$i]}" ]]; then
    echo "Verilog file not found: ${verilog_files[$i]}" >&2
    exit 2
  fi
  verilog_files[$i]="$(readlink -f "${verilog_files[$i]}")"
done

if [[ -n "${xilinx_settings}" ]]; then
  if [[ ! -f "${xilinx_settings}" ]]; then
    echo "Xilinx settings script not found: ${xilinx_settings}" >&2
    exit 2
  fi
  set +u
  # shellcheck disable=SC1090
  source "${xilinx_settings}"
  set -u
fi

if [[ -z "${build_dir}" ]]; then
  build_dir="${repo_root}/build/vitis-synth/${top_module}"
fi
if [[ -z "${metrics_json}" ]]; then
  metrics_json="${build_dir}/vitis-synth-metrics.json"
fi

if [[ "${clean_build}" -eq 1 ]]; then
  rm -rf "${build_dir}"
fi
mkdir -p "${build_dir}" "$(dirname "${metrics_json}")"

tcl_script="${build_dir}/synth.tcl"
source_list="${build_dir}/sources.txt"
xdc_file="${build_dir}/clock.xdc"
utilization_rpt="${build_dir}/utilization_synth.rpt"
timing_rpt="${build_dir}/timing_summary_synth.rpt"
timing_props="${build_dir}/timing.properties"
checkpoint_file="${build_dir}/${top_module}_synth.dcp"

write_missing_tool_json() {
  python3 - "$metrics_json" "$vivado_bin" <<'PY'
import json
import sys
from datetime import datetime, timezone

metrics_json, vivado_bin = sys.argv[1:]
result = {
    "schema": "llm-ntt-vitis-synth-v1",
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "passed": False,
    "error": f"Vivado executable not found: {vivado_bin}",
    "metrics": {},
    "reports": {},
}
with open(metrics_json, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, sort_keys=True)
    f.write("\n")
PY
}

if ! command -v "${vivado_bin}" >/dev/null 2>&1; then
  echo "Vivado executable not found: ${vivado_bin}" >&2
  write_missing_tool_json
  exit 127
fi

{
  printf 'set source_list_file [lindex $argv 0]\n'
  printf 'set top_module [lindex $argv 1]\n'
  printf 'set part_name [lindex $argv 2]\n'
  printf 'set clock_port [lindex $argv 3]\n'
  printf 'set clock_period [lindex $argv 4]\n'
  printf 'set jobs [lindex $argv 5]\n'
  printf 'set out_dir [lindex $argv 6]\n'
  printf 'set xdc_file [lindex $argv 7]\n'
  printf 'set utilization_rpt [lindex $argv 8]\n'
  printf 'set timing_rpt [lindex $argv 9]\n'
  printf 'set timing_props [lindex $argv 10]\n'
  printf 'set checkpoint_file [lindex $argv 11]\n'
  printf '\n'
  printf 'file mkdir $out_dir\n'
  printf 'set_param general.maxThreads $jobs\n'
  printf 'create_project llm_ntt_vitis_synth [file join $out_dir vivado_project] -part $part_name -force\n'
  printf 'set_property target_language Verilog [current_project]\n'
  printf 'set_property source_mgmt_mode None [current_project]\n'
  printf 'set source_fp [open $source_list_file r]\n'
  printf 'set verilog_files [split [string trim [read $source_fp]] "\\n"]\n'
  printf 'close $source_fp\n'
  printf 'foreach verilog_file $verilog_files {\n'
  printf '  read_verilog -sv $verilog_file\n'
  printf '}\n'
  printf 'set xdc_fp [open $xdc_file w]\n'
  printf 'puts $xdc_fp [format {create_clock -name %%s -period %%s [get_ports {%%s}]} $clock_port $clock_period $clock_port]\n'
  printf 'close $xdc_fp\n'
  printf 'read_xdc $xdc_file\n'
  printf 'synth_design -top $top_module -part $part_name -mode out_of_context -flatten_hierarchy rebuilt\n'
  printf 'report_utilization -file $utilization_rpt\n'
  printf 'report_timing_summary -file $timing_rpt -delay_type max -max_paths 10\n'
  printf 'proc safe_get_property {property object} {\n'
  printf '  if {[catch {get_property $property $object} value]} {\n'
  printf '    return ""\n'
  printf '  }\n'
  printf '  return $value\n'
  printf '}\n'
  printf 'set props_fp [open $timing_props w]\n'
  printf 'puts $props_fp "vitis_clock_period_ns=$clock_period"\n'
  printf 'set timing_paths [get_timing_paths -max_paths 1 -nworst 1 -delay_type max -quiet]\n'
  printf 'if {[llength $timing_paths] > 0} {\n'
  printf '  set timing_path [lindex $timing_paths 0]\n'
  printf '  set slack [safe_get_property SLACK $timing_path]\n'
  printf '  set requirement [safe_get_property REQUIREMENT $timing_path]\n'
  printf '  set datapath_delay [safe_get_property DATAPATH_DELAY $timing_path]\n'
  printf '  puts $props_fp "vitis_timing_wns_ns=$slack"\n'
  printf '  puts $props_fp "vitis_timing_requirement_ns=$requirement"\n'
  printf '  puts $props_fp "vitis_timing_datapath_delay_ns=$datapath_delay"\n'
  printf '  if {[string is double -strict $slack] && [string is double -strict $clock_period]} {\n'
  printf '    set achieved_period [expr {$clock_period - $slack}]\n'
  printf '    puts $props_fp "vitis_timing_achieved_period_ns=$achieved_period"\n'
  printf '    if {$achieved_period > 0} {\n'
  printf '      puts $props_fp "vitis_fmax_mhz=[expr {1000.0 / $achieved_period}]"\n'
  printf '    }\n'
  printf '  }\n'
  printf '} else {\n'
  printf '  puts $props_fp "vitis_timing_paths=0"\n'
  printf '}\n'
  printf 'close $props_fp\n'
  printf 'write_checkpoint -force $checkpoint_file\n'
  printf 'close_project\n'
} >"${tcl_script}"

printf '%s\n' "${verilog_files[@]}" >"${source_list}"

vivado_cmd=(
  "${vivado_bin}" -mode batch -nojournal -nolog -source "${tcl_script}" -tclargs
  "${source_list}" "${top_module}" "${part}" "${clock_port}" "${clock_period}"
  "${jobs}" "${build_dir}" "${xdc_file}" "${utilization_rpt}" "${timing_rpt}"
  "${timing_props}" "${checkpoint_file}"
)

set +e
if [[ "${timeout_seconds}" -gt 0 ]]; then
  timeout --kill-after=60s "${timeout_seconds}" "${vivado_cmd[@]}"
else
  "${vivado_cmd[@]}"
fi
vivado_status=$?
set -e

script_status="${vivado_status}"
completion_warning=""
if [[ "${vivado_status}" -ne 0 &&
      -s "${utilization_rpt}" &&
      -s "${timing_rpt}" &&
      -s "${timing_props}" &&
      -s "${checkpoint_file}" ]]; then
  script_status=0
  completion_warning="Vivado exited with status ${vivado_status} after generating synthesis reports and checkpoint"
elif [[ "${vivado_status}" -ne 0 && -s "${utilization_rpt}" ]]; then
  script_status=0
  completion_warning="Vivado exited with status ${vivado_status} after synthesis utilization was generated; timing or checkpoint output is incomplete"
fi

python3 - "$metrics_json" "$script_status" "$vivado_status" "$completion_warning" "$top_module" "$source_list" \
  "$part" "$clock_port" "$clock_period" "$build_dir" "$utilization_rpt" \
  "$timing_rpt" "$timing_props" "$checkpoint_file" "$timeout_seconds" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone

(
    metrics_json,
    script_status,
    vivado_status,
    completion_warning,
    top_module,
    source_list,
    part,
    clock_port,
    clock_period,
    build_dir,
    utilization_rpt,
    timing_rpt,
    timing_props,
    checkpoint_file,
    timeout_seconds,
) = sys.argv[1:]

def parse_number(value):
    value = value.strip().replace(",", "")
    if value in ("", "-", "NA", "N/A", "None"):
        return None
    if value.endswith("%"):
        value = value[:-1]
    try:
        number = float(value)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number

def sanitize(value):
    value = value.lstrip("$").lstrip("\\")
    value = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    return value.lower() or "unknown"

def rel(path):
    if not path:
        return ""
    try:
        return os.path.relpath(path, os.getcwd())
    except ValueError:
        return path

verilog_files = []
if os.path.exists(source_list):
    with open(source_list, "r", encoding="utf-8", errors="replace") as f:
        verilog_files = [line.strip() for line in f if line.strip()]

metrics = {}
rows = {}

if os.path.exists(utilization_rpt):
    with open(utilization_rpt, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "|" not in line:
                continue
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if len(cells) < 2:
                continue
            name = cells[0]
            used = parse_number(cells[1])
            if used is None or name.lower() in ("site type", "name"):
                continue
            key = sanitize(name)
            rows[key] = cells
            metrics[f"vitis_util_{key}_used"] = used
            if len(cells) >= 5:
                available = parse_number(cells[-2])
                if available is not None:
                    metrics[f"vitis_util_{key}_available"] = available
            if len(cells) >= 3:
                util_pct = parse_number(cells[-1])
                if util_pct is not None:
                    metrics[f"vitis_util_{key}_pct"] = util_pct

def add_alias(alias, *row_keys):
    for row_key in row_keys:
        metric_key = f"vitis_util_{row_key}_used"
        if metric_key in metrics:
            metrics[alias] = metrics[metric_key]
            available_key = f"vitis_util_{row_key}_available"
            pct_key = f"vitis_util_{row_key}_pct"
            if available_key in metrics:
                metrics[f"{alias}_available"] = metrics[available_key]
            if pct_key in metrics:
                metrics[f"{alias}_pct"] = metrics[pct_key]
            return

add_alias("vitis_lut", "clb_luts", "slice_luts")
add_alias("vitis_ff", "clb_registers", "slice_registers")
add_alias("vitis_dsp", "dsps", "dsp", "dsp48e2")
add_alias("vitis_bram_tile", "block_ram_tile", "bram_tile")
add_alias("vitis_uram", "uram", "uram288")

if os.path.exists(timing_props):
    with open(timing_props, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed = parse_number(value)
            metrics[key] = parsed if parsed is not None else value

clock_period_value = parse_number(clock_period)
if clock_period_value is not None:
    metrics.setdefault("vitis_clock_period_ns", clock_period_value)

reports = {
    "build_dir": rel(build_dir),
    "checkpoint": rel(checkpoint_file) if os.path.exists(checkpoint_file) else "",
    "synth_tcl": rel(os.path.join(build_dir, "synth.tcl")),
    "timing": rel(timing_rpt) if os.path.exists(timing_rpt) else "",
    "timing_properties": rel(timing_props) if os.path.exists(timing_props) else "",
    "utilization": rel(utilization_rpt) if os.path.exists(utilization_rpt) else "",
}

result = {
    "schema": "llm-ntt-vitis-synth-v1",
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "passed": int(script_status) == 0,
    "status": int(script_status),
    "vivado_exit_status": int(vivado_status),
    "top_module": top_module,
    "verilog_file": rel(verilog_files[0]) if verilog_files else "",
    "verilog_files": [rel(path) for path in verilog_files],
    "part": part,
    "clock_port": clock_port,
    "clock_period_ns": clock_period_value if clock_period_value is not None else clock_period,
    "timeout_seconds": int(timeout_seconds),
    "metrics": metrics,
    "reports": reports,
}

if completion_warning:
    result["warning"] = completion_warning
if int(timeout_seconds) > 0 and int(vivado_status) in (124, 137):
    result["error"] = f"Vivado synthesis timed out after {timeout_seconds} seconds"

with open(metrics_json, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, sort_keys=True)
    f.write("\n")

print(json.dumps(result, indent=2, sort_keys=True))
PY

exit "${script_status}"
