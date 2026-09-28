#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$repo_root/build/fhe512-preroute.sif"
processors=1
use_sudo=0

usage() {
  cat <<'EOF'
Usage: scripts/build_fhe512_image.sh [--output FILE] [--processors N] [--sudo]

Build the N=512 grid image from apptainer/fhe512-preroute.def.
EOF
}

while (($#)); do
  case "$1" in
    --output) output="${2:?missing output path}"; shift 2 ;;
    --processors) processors="${2:?missing processor count}"; shift 2 ;;
    --sudo) use_sudo=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if ! [[ "$processors" =~ ^[1-9][0-9]*$ ]]; then
  echo "--processors must be a positive integer" >&2
  exit 2
fi
mkdir -p "$(dirname "$output")"
command=(apptainer build --force --mksquashfs-args "-processors $processors"
  "$output" "$repo_root/apptainer/fhe512-preroute.def")
if ((use_sudo)); then
  sudo "${command[@]}"
else
  "${command[@]}"
fi
