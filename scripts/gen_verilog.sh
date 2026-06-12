#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_sbt() {
  local variant="$1"
  echo "==> Generating Verilog for ${variant}"
  (cd "${repo_root}/variants/${variant}/chisel" && sbt run)
}

run_sbt "yata-raintt"
run_sbt "hoge-streaming"
run_sbt "hoge-nttid"
