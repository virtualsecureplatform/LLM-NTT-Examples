#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="$repo_root/build/fhe512-sgen-precision.sif"
export APPTAINERENV_FHE512_IMAGE_SHA256="$(sha256sum "$image" | cut -d' ' -f1)"
tool_bin="$repo_root/build/polynomial-study-bin"
mkdir -p "$tool_bin"
ln -sfn "$repo_root/build/tools/bin/yosys" "$tool_bin/yosys"
ln -sfn "$repo_root/scripts/verilator_pinned.sh" "$tool_bin/verilator"
ln -sfn /usr/bin/python3 "$tool_bin/python"
export APPTAINERENV_PREPEND_PATH="$tool_bin"
exec apptainer exec --cleanenv --no-home --bind "$repo_root:$repo_root" --pwd "$repo_root" \
  "$image" python3 "$repo_root/scripts/llm_polynomial_study.py" --qualify-request "$1"
