#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/build_llm_ntt_sif.sh [options]

Builds the LLM-NTT Apptainer image from apptainer/llm-ntt.def.

Options:
  --output FILE        Output SIF path. Defaults to llm-ntt.sif.
  --definition FILE    Apptainer definition file. Defaults to
                       apptainer/llm-ntt.def.
  --processors N       mksquashfs processor count. Defaults to 1.
  --sudo              Run apptainer build through sudo.
  --sudo-temp-dir DIR  Temporary staging directory used with --sudo. Defaults
                       to SIF_TMPDIR, TMPDIR, or /tmp.
  --build-bind SPEC   Bind path visible during Apptainer build. SPEC uses the
                       Apptainer src[:dest[:opts]] format. May be repeated.
  --bind-xilinx       Bind /home/opt/xilinx and /opt/xilinx during build when
                       present on the host.
  --with-tapa-runtime Build and install RapidStream TAPA C++ runtime into the
                       image. Implies --bind-xilinx.
  --tapa-repo URL     RapidStream TAPA git URL for --with-tapa-runtime.
  --tapa-ref REF      RapidStream TAPA branch/tag for --with-tapa-runtime.
                       Defaults to main.
  --tapa-bazel-version VERSION
                       Bazel version used by Bazelisk for TAPA. Defaults to
                       8.4.2.
  --tapa-build-jobs N Bazel jobs for TAPA build. Defaults to 2.
  --libtinfo5-deb-url URL
                       Legacy libtinfo5 .deb used by TAPA's downloaded LLVM.
  --xilinx-tool-path DIR
                       Xilinx root used by the TAPA source build. Defaults to
                       /home/opt/xilinx.
  --xilinx-tool-version VERSION
                       Xilinx version used by the TAPA source build. Defaults
                       to 2023.2.
  --build-arg KEY=VAL Extra Apptainer build argument. May be repeated.
  --apptainer-bin BIN Apptainer executable. Defaults to APPTAINER_BIN or
                       apptainer.
  --skip-check        Do not run the image-only dependency check after build.
  -h, --help          Show this help.
EOF
}

output="llm-ntt.sif"
definition="${repo_root}/apptainer/llm-ntt.def"
processors="1"
use_sudo=0
apptainer_bin="${APPTAINER_BIN:-apptainer}"
skip_check=0
sudo_temp_dir="${SIF_TMPDIR:-${TMPDIR:-/tmp}}"
tmp_build_dir=""
bind_xilinx=0
with_tapa_runtime=0
tapa_repo="https://github.com/rapidstream-org/rapidstream-tapa.git"
tapa_ref="main"
tapa_bazel_version="8.4.2"
tapa_build_jobs="2"
libtinfo5_deb_url="https://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/libtinfo5_6.3-2ubuntu0.1_amd64.deb"
xilinx_tool_path="/home/opt/xilinx"
xilinx_tool_version="2023.2"
declare -a build_binds=()
declare -a build_args=()

cleanup_tmp() {
  if [[ -n "${tmp_build_dir}" && -d "${tmp_build_dir}" ]]; then
    rm -rf "${tmp_build_dir}" 2>/dev/null || {
      if [[ "${use_sudo}" -eq 1 ]] && command -v sudo >/dev/null 2>&1; then
        sudo -n rm -rf "${tmp_build_dir}" 2>/dev/null || true
      fi
    }
  fi
}
trap cleanup_tmp EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output="${2:-}"
      shift 2
      ;;
    --definition)
      definition="${2:-}"
      shift 2
      ;;
    --processors)
      processors="${2:-}"
      shift 2
      ;;
    --sudo)
      use_sudo=1
      shift
      ;;
    --sudo-temp-dir)
      sudo_temp_dir="${2:-}"
      shift 2
      ;;
    --build-bind)
      build_binds+=("${2:-}")
      shift 2
      ;;
    --bind-xilinx)
      bind_xilinx=1
      shift
      ;;
    --with-tapa-runtime)
      with_tapa_runtime=1
      bind_xilinx=1
      shift
      ;;
    --tapa-repo)
      tapa_repo="${2:-}"
      shift 2
      ;;
    --tapa-ref)
      tapa_ref="${2:-}"
      shift 2
      ;;
    --tapa-bazel-version)
      tapa_bazel_version="${2:-}"
      shift 2
      ;;
    --tapa-build-jobs)
      tapa_build_jobs="${2:-}"
      shift 2
      ;;
    --libtinfo5-deb-url)
      libtinfo5_deb_url="${2:-}"
      shift 2
      ;;
    --xilinx-tool-path)
      xilinx_tool_path="${2:-}"
      shift 2
      ;;
    --xilinx-tool-version)
      xilinx_tool_version="${2:-}"
      shift 2
      ;;
    --build-arg)
      build_args+=("${2:-}")
      shift 2
      ;;
    --apptainer-bin)
      apptainer_bin="${2:-}"
      shift 2
      ;;
    --skip-check)
      skip_check=1
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

if [[ -z "${output}" || -z "${definition}" || -z "${processors}" || -z "${sudo_temp_dir}" ]]; then
  echo "Empty --output, --definition, --processors, or --sudo-temp-dir value" >&2
  exit 2
fi
if [[ -z "${tapa_repo}" || -z "${tapa_ref}" || -z "${tapa_bazel_version}" || -z "${tapa_build_jobs}" || -z "${libtinfo5_deb_url}" || -z "${xilinx_tool_path}" || -z "${xilinx_tool_version}" ]]; then
  echo "Empty TAPA/Xilinx option value" >&2
  exit 2
fi
if ! [[ "${tapa_build_jobs}" =~ ^[0-9]+$ && "${tapa_build_jobs}" -gt 0 ]]; then
  echo "Invalid --tapa-build-jobs value: ${tapa_build_jobs}" >&2
  exit 2
fi
for bind_arg in "${build_binds[@]}"; do
  if [[ -z "${bind_arg}" ]]; then
    echo "Empty --build-bind value" >&2
    exit 2
  fi
done
for build_arg in "${build_args[@]}"; do
  if [[ -z "${build_arg}" || "${build_arg}" != *=* ]]; then
    echo "--build-arg must use KEY=VALUE format: ${build_arg}" >&2
    exit 2
  fi
done
if [[ "${output}" == */ ]]; then
  echo "--output must name a SIF file, not a directory: ${output}" >&2
  exit 2
fi
if ! [[ "${processors}" =~ ^[0-9]+$ && "${processors}" -gt 0 ]]; then
  echo "Invalid --processors value: ${processors}" >&2
  exit 2
fi
if [[ ! -f "${definition}" ]]; then
  echo "Definition file not found: ${definition}" >&2
  exit 2
fi
if ! command -v "${apptainer_bin}" >/dev/null 2>&1; then
  echo "Apptainer executable not found: ${apptainer_bin}" >&2
  exit 127
fi
if [[ "${with_tapa_runtime}" -eq 1 && ! -d "${xilinx_tool_path}" ]]; then
  echo "Xilinx tool path not found for --with-tapa-runtime: ${xilinx_tool_path}" >&2
  echo "Use --xilinx-tool-path or --build-bind to make it visible." >&2
  exit 2
fi

build_output="${output}"
if [[ "${use_sudo}" -eq 1 ]]; then
  if [[ ! -d "${sudo_temp_dir}" ]]; then
    echo "--sudo-temp-dir does not exist: ${sudo_temp_dir}" >&2
    exit 2
  fi
  output_dir="$(dirname -- "${output}")"
  output_base="$(basename -- "${output}")"
  mkdir -p "${output_dir}"
  tmp_build_dir="$(mktemp -d "${sudo_temp_dir%/}/llm-ntt-sif.XXXXXX")"
  build_output="${tmp_build_dir}/${output_base}"
  printf 'Staging sudo build output at: %s\n' "${build_output}"
fi

if [[ "${bind_xilinx}" -eq 1 && "${with_tapa_runtime}" -eq 0 ]]; then
  if [[ -d /home/opt/xilinx ]]; then
    build_binds+=("/home/opt/xilinx:/home/opt/xilinx:ro")
  fi
  if [[ -d /opt/xilinx ]]; then
    build_binds+=("/opt/xilinx:/opt/xilinx:ro")
  fi
fi
if [[ "${with_tapa_runtime}" -eq 1 ]]; then
  build_binds+=("${xilinx_tool_path}:${xilinx_tool_path}:ro")
  build_args+=(
    "WITH_TAPA_RUNTIME=1"
    "TAPA_REPO=${tapa_repo}"
    "TAPA_REF=${tapa_ref}"
    "TAPA_BAZEL_VERSION=${tapa_bazel_version}"
    "TAPA_BUILD_JOBS=${tapa_build_jobs}"
    "LIBTINFO5_DEB_URL=${libtinfo5_deb_url}"
    "XILINX_TOOL_PATH=${xilinx_tool_path}"
    "XILINX_TOOL_VERSION=${xilinx_tool_version}"
    "XILINX_TOOL_LEGACY_PATH=${xilinx_tool_path}"
    "XILINX_TOOL_LEGACY_VERSION=${xilinx_tool_version}"
  )
fi

cmd=("${apptainer_bin}" build --force)
for bind_arg in "${build_binds[@]}"; do
  cmd+=(--bind "${bind_arg}")
done
for build_arg in "${build_args[@]}"; do
  cmd+=(--build-arg "${build_arg}")
done
cmd+=(--mksquashfs-args "-processors ${processors}" "${build_output}" "${definition}")
if [[ "${use_sudo}" -eq 1 ]]; then
  cmd=(sudo "${cmd[@]}")
fi

printf 'Building Apptainer image:\n'
printf '  %q' "${cmd[@]}"
printf '\n'
set +e
"${cmd[@]}"
build_status=$?
set -e
if [[ "${build_status}" -ne 0 ]]; then
  cat >&2 <<EOF

Apptainer image build failed with status ${build_status}.
On hosts where unprivileged fakeroot/user namespaces cannot run %post, retry
with sudo:

  scripts/build_llm_ntt_sif.sh --sudo --output ${output}

EOF
  exit "${build_status}"
fi

if [[ "${use_sudo}" -eq 1 ]]; then
  sudo chown "$(id -u):$(id -g)" "${build_output}"
  chmod u+rw "${build_output}"
  mv -f "${build_output}" "${output}"
fi

if [[ "${skip_check}" -eq 0 ]]; then
  check_args=(--image-only)
  if [[ "${with_tapa_runtime}" -eq 1 ]]; then
    printf '\nRunning AutoNTT HLS TAPA-runtime dependency check:\n'
    check_args=(--no-require-vitis)
  else
    printf '\nRunning image-only AutoNTT HLS dependency check:\n'
  fi
  "${apptainer_bin}" exec \
    --no-home \
    --pwd /work \
    --bind "${repo_root}:/work" \
    "${output}" \
    scripts/check_autontt_hls_deps.sh "${check_args[@]}"
fi

cat <<EOF

Built: ${output}

For full AutoNTT HLS checks after binding Vitis and a full TAPA/Pasta runtime:
  ${apptainer_bin} exec --no-home --pwd /work \\
    --bind "${repo_root}:/work" \\
    --bind /home/opt/xilinx:/home/opt/xilinx \\
    --bind /opt/pasta:/opt/pasta \\
    "${output}" \\
    scripts/check_autontt_hls_deps.sh
EOF
