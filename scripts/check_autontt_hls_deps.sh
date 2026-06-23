#!/usr/bin/env bash
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/check_autontt_hls_deps.sh [options]

Checks the dependency surface used by AutoNTT-generated TAPA/Vitis HLS
artifacts. The check mirrors the generated Makefile C-simulation link line:
  g++ ... -I$(XILINX_HLS)/include -ltapa -lfrt -lglog -lgflags -lOpenCL

Options:
  --xilinx-settings FILE  Source a Xilinx settings script before checking.
                          Defaults to XILINX_SETTINGS, or
                          /home/opt/xilinx/Vitis/2023.2/settings64.sh when
                          present.
  --xilinx-hls DIR        Vitis HLS root containing include/ap_int.h. Defaults
                          to XILINX_HLS, or /home/opt/xilinx/Vitis_HLS/2023.2
                          when present.
  --tapa-home DIR         TAPA/Pasta install root. Defaults to TAPA_HOME,
                          RAPIDSTREAM_INSTALL_DIR, or common /opt and $HOME
                          TAPA/Pasta prefixes when present.
  --tapa-include DIR      Extra directory containing tapa.h.
  --tapa-lib DIR          Extra directory containing libtapa and libfrt.
  --cxx CXX               C++ compiler for smoke checks. Defaults to g++ to
                          match AutoNTT-generated Makefiles.
  --no-require-vitis      Do not fail when Vitis/Vivado commands are absent.
                          This is useful for checking image-only dependencies.
  --no-require-tapa-runtime
                          Do not fail when tapa.h, libtapa, or libfrt are
                          absent. This is useful for checking image-only
                          frontend dependencies before binding/installing the
                          full TAPA/Pasta C++ runtime.
  --image-only            Shorthand for --no-require-vitis and
                          --no-require-tapa-runtime.
  --no-compile-smoke      Skip the final generated-Makefile compile/link smoke.
  -h, --help              Show this help.
EOF
}

xilinx_settings="${XILINX_SETTINGS:-}"
if [[ -z "${xilinx_settings}" && -f /home/opt/xilinx/Vitis/2023.2/settings64.sh ]]; then
  xilinx_settings="/home/opt/xilinx/Vitis/2023.2/settings64.sh"
fi
xilinx_hls="${XILINX_HLS:-}"
if [[ -z "${xilinx_hls}" && -d /home/opt/xilinx/Vitis_HLS/2023.2 ]]; then
  xilinx_hls="/home/opt/xilinx/Vitis_HLS/2023.2"
fi
tapa_home="${TAPA_HOME:-${RAPIDSTREAM_INSTALL_DIR:-}}"
cxx="g++"
require_vitis=1
require_tapa_runtime=1
compile_smoke=1

declare -a extra_tapa_includes=()
declare -a extra_tapa_libs=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --xilinx-settings)
      xilinx_settings="${2:-}"
      shift 2
      ;;
    --xilinx-hls)
      xilinx_hls="${2:-}"
      shift 2
      ;;
    --tapa-home)
      tapa_home="${2:-}"
      shift 2
      ;;
    --tapa-include)
      extra_tapa_includes+=("${2:-}")
      shift 2
      ;;
    --tapa-lib)
      extra_tapa_libs+=("${2:-}")
      shift 2
      ;;
    --cxx)
      cxx="${2:-}"
      shift 2
      ;;
    --no-require-vitis)
      require_vitis=0
      shift
      ;;
    --no-require-tapa-runtime)
      require_tapa_runtime=0
      shift
      ;;
    --image-only)
      require_vitis=0
      require_tapa_runtime=0
      shift
      ;;
    --no-compile-smoke)
      compile_smoke=0
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

declare -a failures=()
declare -a warnings=()
declare -a cpp_flags=()
declare -a ld_flags=()
declare -a tapa_runtime_libs=(
  -ltapa
  -lfrt
  -lglog
  -lgflags
  -lOpenCL
  -lyaml-cpp
  -ltinyxml2
  -lthread
  -lcontext
  -pthread
)

ok() {
  printf '[ok] %s\n' "$*"
}

warn() {
  printf '[warn] %s\n' "$*" >&2
  warnings+=("$*")
}

missing() {
  printf '[missing] %s\n' "$*" >&2
  failures+=("$*")
}

add_path_dir() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    PATH="${dir}:${PATH}"
  fi
}

add_include_dir() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    cpp_flags+=("-I${dir}")
  fi
}

add_library_dir() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    ld_flags+=("-L${dir}" "-Wl,-rpath,${dir}")
  fi
}

add_tapa_prefix() {
  local prefix="$1"
  [[ -n "${prefix}" ]] || return 0
  add_path_dir "${prefix}/usr/bin"
  add_path_dir "${prefix}/bin"
  add_include_dir "${prefix}/usr/include"
  add_include_dir "${prefix}/include"
  add_library_dir "${prefix}/usr/lib"
  add_library_dir "${prefix}/usr/lib64"
  add_library_dir "${prefix}/lib"
  add_library_dir "${prefix}/lib64"
}

check_command() {
  local name="$1"
  local required="$2"
  local path
  if path="$(command -v "${name}" 2>/dev/null)"; then
    ok "${name}: ${path}"
  elif [[ "${required}" -eq 1 ]]; then
    missing "command not found: ${name}"
  else
    warn "command not found: ${name}"
  fi
}

check_command_smoke() {
  local label="$1"
  local required="$2"
  shift 2
  local tmp
  tmp="$(mktemp)"
  if "$@" >"${tmp}" 2>&1; then
    ok "${label}"
  elif [[ "${required}" -eq 1 ]]; then
    missing "${label} failed ($(tail -n 1 "${tmp}"))"
  else
    warn "${label} failed ($(tail -n 1 "${tmp}"))"
  fi
  rm -f "${tmp}"
}

compile_header() {
  local header="$1"
  local required="$2"
  local tmpdir
  tmpdir="$(mktemp -d)"
  printf '#include <%s>\nint main() { return 0; }\n' "${header}" >"${tmpdir}/header.cpp"
  if "${cxx}" -std=c++17 "${cpp_flags[@]}" -fsyntax-only \
      "${tmpdir}/header.cpp" >"${tmpdir}/compile.log" 2>&1; then
    ok "header available: ${header}"
  elif [[ "${required}" -eq 1 ]]; then
    missing "header unavailable: ${header} ($(tail -n 1 "${tmpdir}/compile.log"))"
  else
    warn "header unavailable: ${header} ($(tail -n 1 "${tmpdir}/compile.log"))"
  fi
  rm -rf "${tmpdir}"
}

link_library() {
  local label="$1"
  local required="$2"
  shift 2
  local tmpdir
  tmpdir="$(mktemp -d)"
  printf 'int main() { return 0; }\n' >"${tmpdir}/main.cpp"
  if "${cxx}" -std=c++17 "${tmpdir}/main.cpp" "${ld_flags[@]}" "$@" \
      -o "${tmpdir}/a.out" >"${tmpdir}/link.log" 2>&1; then
    ok "library link available: ${label}"
  elif [[ "${required}" -eq 1 ]]; then
    missing "library link unavailable: ${label} ($(tail -n 1 "${tmpdir}/link.log"))"
  else
    warn "library link unavailable: ${label} ($(tail -n 1 "${tmpdir}/link.log"))"
  fi
  rm -rf "${tmpdir}"
}

echo "Repository: ${repo_root}"

if [[ -n "${xilinx_settings}" ]]; then
  if [[ -f "${xilinx_settings}" ]]; then
    # Xilinx scripts commonly read variables that are unset in strict shells.
    set +u
    # shellcheck disable=SC1090
    source "${xilinx_settings}"
    set -u
    ok "sourced Xilinx settings: ${xilinx_settings}"
  else
    missing "Xilinx settings script not found: ${xilinx_settings}"
  fi
fi

if [[ -n "${xilinx_hls}" ]]; then
  if [[ -d "${xilinx_hls}" ]]; then
    export XILINX_HLS="${xilinx_hls}"
    add_include_dir "${xilinx_hls}/include"
    ok "XILINX_HLS: ${xilinx_hls}"
  else
    missing "XILINX_HLS directory not found: ${xilinx_hls}"
  fi
elif [[ "${require_vitis}" -eq 1 ]]; then
  missing "XILINX_HLS is not set and /home/opt/xilinx/Vitis_HLS/2023.2 is absent"
else
  warn "XILINX_HLS is not set"
fi

for candidate in /home/opt/xilinx/xrt "${XILINX_XRT:-}" /opt/xilinx/xrt; do
  if [[ -n "${candidate}" && -d "${candidate}" ]]; then
    add_include_dir "${candidate}/include"
    add_library_dir "${candidate}/lib"
    add_library_dir "${candidate}/lib64"
    ok "XRT: ${candidate}"
    break
  fi
done

if [[ -n "${tapa_home}" ]]; then
  if [[ -d "${tapa_home}" ]]; then
    add_tapa_prefix "${tapa_home}"
    ok "TAPA_HOME: ${tapa_home}"
  elif [[ "${require_tapa_runtime}" -eq 1 ]]; then
    missing "TAPA install root not found: ${tapa_home}"
  else
    warn "TAPA install root not found: ${tapa_home}"
  fi
else
  for candidate in \
      /opt/pasta \
      /opt/tapa \
      /opt/rapidstream-tapa \
      "${HOME:-}/.pasta" \
      "${HOME:-}/.tapa" \
      "${HOME:-}/.rapidstream-tapa"; do
    if [[ -d "${candidate}" ]]; then
      tapa_home="${candidate}"
      add_tapa_prefix "${candidate}"
      ok "TAPA_HOME: ${candidate}"
      break
    fi
  done
fi

for item in "${extra_tapa_includes[@]}"; do
  add_include_dir "${item}"
done
for item in "${extra_tapa_libs[@]}"; do
  add_library_dir "${item}"
done
if [[ -n "${TAPA_INCLUDE_PATH:-}" ]]; then
  IFS=: read -r -a path_items <<<"${TAPA_INCLUDE_PATH}"
  for item in "${path_items[@]}"; do
    add_include_dir "${item}"
  done
fi
if [[ -n "${TAPA_LIBRARY_PATH:-}" ]]; then
  IFS=: read -r -a path_items <<<"${TAPA_LIBRARY_PATH}"
  for item in "${path_items[@]}"; do
    add_library_dir "${item}"
  done
fi

check_command python3 1
check_command "${cxx}" 1
check_command tapac 1
check_command tapa 0
check_command tapacc "${require_tapa_runtime}"
check_command vitis_hls "${require_vitis}"
check_command v++ "${require_vitis}"
check_command vivado "${require_vitis}"

if command -v tapac >/dev/null 2>&1; then
  check_command_smoke "tapac import/help smoke" 1 tapac --help
fi
if command -v tapacc >/dev/null 2>&1; then
  check_command_smoke "tapacc version smoke" "${require_tapa_runtime}" tapacc --version
fi

if python_output="$(python3 - <<'PY' 2>&1
import importlib.metadata as metadata
import tapa

try:
    version = metadata.version("tapa")
except metadata.PackageNotFoundError:
    version = "unknown"
print(f"tapa {version} from {getattr(tapa, '__file__', '<namespace>')}")
PY
)"; then
  ok "Python import: ${python_output}"
else
  missing "Python package import failed: tapa (${python_output})"
fi

compile_header gflags/gflags.h 1
compile_header glog/logging.h 1
compile_header boost/coroutine2/coroutine.hpp 1
compile_header boost/thread/condition_variable.hpp 1
compile_header boost/stacktrace.hpp 1
compile_header nlohmann/json.hpp 1
compile_header tinyxml2.h 1
compile_header yaml-cpp/yaml.h 1
compile_header CL/cl.h 1
compile_header CL/cl2.hpp 1
if [[ "${require_vitis}" -eq 1 ]]; then
  compile_header CL/cl_ext_xilinx.h 1
fi
if [[ -n "${xilinx_hls}" ]]; then
  compile_header ap_int.h "${require_vitis}"
fi
compile_header tapa.h "${require_tapa_runtime}"

link_library gflags 1 -lgflags
link_library glog 1 -lglog
link_library OpenCL 1 -lOpenCL
link_library boost_context 1 -lboost_context
link_library boost_coroutine 1 -lboost_coroutine
link_library boost_fiber 1 -lboost_fiber
link_library boost_thread 1 -lboost_thread
link_library tinyxml2 1 -ltinyxml2
link_library yaml-cpp 1 -lyaml-cpp
link_library "AutoNTT TAPA runtime group" "${require_tapa_runtime}" "${tapa_runtime_libs[@]}"

if [[ "${compile_smoke}" -eq 1 && "${require_tapa_runtime}" -eq 0 ]]; then
  warn "skipping AutoNTT C-simulation compile/link smoke because TAPA runtime is optional"
elif [[ "${compile_smoke}" -eq 1 ]]; then
  tmpdir="$(mktemp -d)"
  cat >"${tmpdir}/autontt_hls_smoke.cpp" <<'CPP'
#include <CL/cl.h>
#include <cstdint>
#include <gflags/gflags.h>
#include <glog/logging.h>
#include <tapa.h>

int main(int argc, char** argv) {
  gflags::AllowCommandLineReparsing();
  google::InitGoogleLogging(argv[0]);
  return CL_SUCCESS == 0 ? argc - argc : 0;
}
CPP
  if "${cxx}" "${tmpdir}/autontt_hls_smoke.cpp" -o "${tmpdir}/autontt_hls_smoke" \
      "${cpp_flags[@]}" "${ld_flags[@]}" \
      -O2 "${tapa_runtime_libs[@]}" -std=c++17 \
      -DBU_BUF_FIFO_DEPTH=1024 >"${tmpdir}/compile.log" 2>&1; then
    ok "AutoNTT C-simulation compile/link smoke passed"
  else
    missing "AutoNTT C-simulation compile/link smoke failed ($(tail -n 1 "${tmpdir}/compile.log"))"
  fi
  rm -rf "${tmpdir}"
fi

if [[ "${#warnings[@]}" -gt 0 ]]; then
  printf '\nWarnings:\n' >&2
  printf '  - %s\n' "${warnings[@]}" >&2
fi

if [[ "${#failures[@]}" -gt 0 ]]; then
  printf '\nMissing dependencies:\n' >&2
  printf '  - %s\n' "${failures[@]}" >&2
  cat >&2 <<'EOF'

For the Apptainer image, rebuild after editing apptainer/llm-ntt.def:
  apptainer build --mksquashfs-args "-processors 1" llm-ntt.sif apptainer/llm-ntt.def

For full AutoNTT HLS synthesis, Vitis must be visible separately and the full
TAPA/Pasta C++ runtime must provide tapa.h, libtapa, and libfrt. Bind or
install that package under a searched prefix such as /opt/pasta, /opt/tapa, or
/opt/rapidstream-tapa, or pass --tapa-home, --tapa-include, and --tapa-lib.
EOF
  exit 1
fi

echo
echo "AutoNTT HLS dependency check passed."
