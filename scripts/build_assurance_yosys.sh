#!/usr/bin/env bash
# Build the proof engine used by primitive_proofs.py in an isolated local prefix.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
proof_prefix="${1:-${repo_root}/build/tools}"
proof_jobs="${2:-4}"
if ! [[ "$proof_jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo 'jobs must be a positive integer' >&2
  exit 2
fi
for command in git make g++ bison flex python3; do command -v "$command" >/dev/null; done
mkdir -p "$proof_prefix"
proof_prefix="$(cd "$proof_prefix" && pwd)"
proof_source="$proof_prefix/src/yosys"
proof_revision=b5170e1394f602c607e75bdbb1a2b637118f2086
if [[ ! -d "$proof_source" ]]; then
  git clone --branch v0.50 --recursive https://github.com/YosysHQ/yosys.git "$proof_source"
fi
if [[ "$(git -C "$proof_source" rev-parse HEAD)" != "$proof_revision" ]] || ! git -C "$proof_source" diff --quiet HEAD; then
  echo 'Yosys source differs from the proof pin; use a fresh prefix' >&2
  exit 1
fi
make -C "$proof_source" -j "$proof_jobs" PREFIX="$proof_prefix" \
  ENABLE_READLINE=0 ENABLE_TCL=0 ENABLE_ABC=0 ENABLE_LIBYOSYS=0 install
"$proof_prefix/bin/yosys" -V
python3 - "$proof_prefix" "$proof_revision" <<'PY'
import hashlib,json,sys
from pathlib import Path
prefix=Path(sys.argv[1]);binary=prefix/'bin/yosys'
(prefix/'yosys-build.json').write_text(json.dumps(dict(revision=sys.argv[2],
    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    options=dict(ENABLE_READLINE=0,ENABLE_TCL=0,ENABLE_ABC=0,ENABLE_LIBYOSYS=0)),indent=2)+'\n')
PY
