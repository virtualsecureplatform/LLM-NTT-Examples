#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="${FHE512_SGEN_IMAGE:-${repo_root}/build/fhe512-sgen-precision.sif}"
if [[ ! -f "$image" ]]; then
  echo "Apptainer image missing: $image" >&2
  echo "Build it: scripts/build_llm_ntt_sif.sh --definition apptainer/fhe512-preroute.def --output build/fhe512-sgen-precision.sif --skip-check" >&2
  exit 2
fi
image="$(realpath "$image")"
export APPTAINERENV_FHE512_IMAGE_SHA256="$(sha256sum "$image" | cut -d' ' -f1)"
tool_bin="$repo_root/build/fhe512-sgen-bin"
mkdir -p "$tool_bin"
ln -sfn "$repo_root/build/tools/bin/yosys" "$tool_bin/yosys"
ln -sfn "$repo_root/scripts/verilator_pinned.sh" "$tool_bin/verilator"
ln -sfn /usr/bin/python3 "$tool_bin/python"
export APPTAINERENV_PREPEND_PATH="$tool_bin"
bind_args=(--bind "$repo_root:$repo_root")
if [[ -n "${FHE512_JAVA_HOME:-}" ]]; then
  bind_args+=(--bind "$FHE512_JAVA_HOME:/opt/fhe512-jdk:ro")
  export APPTAINERENV_JAVA_HOME=/opt/fhe512-jdk
  export APPTAINERENV_PREPEND_PATH="/opt/fhe512-jdk/bin:$APPTAINERENV_PREPEND_PATH"
fi
exec apptainer exec --cleanenv --no-home --pwd "$repo_root" \
  "${bind_args[@]}" "$image" \
  python3 "$repo_root/scripts/fhe512_sgen_precision.py" "$@"
