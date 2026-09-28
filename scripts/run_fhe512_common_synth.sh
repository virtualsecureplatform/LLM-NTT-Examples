#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="${FHE512_SGEN_IMAGE:-${repo_root}/build/fhe512-sgen-precision.sif}"
if [[ ! -f "$image" ]]; then
  echo "Apptainer image missing: $image" >&2
  echo "Build it: scripts/build_fhe512_image.sh --output build/fhe512-sgen-precision.sif" >&2
  exit 2
fi
image="$(realpath "$image")"
export APPTAINERENV_FHE512_IMAGE_SHA256="$(sha256sum "$image" | cut -d' ' -f1)"
exec apptainer exec --cleanenv --no-home --pwd "$repo_root" \
  --bind "$repo_root:$repo_root" "$image" \
  python3 "$repo_root/scripts/fhe512_common_synth.py" "$@"
