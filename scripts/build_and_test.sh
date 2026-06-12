#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="${repo_root}/build"

"${repo_root}/scripts/gen_verilog.sh"

if [[ -f "${build_dir}/CMakeCache.txt" ]] &&
   ! grep -qx "CMAKE_HOME_DIRECTORY:INTERNAL=${repo_root}" "${build_dir}/CMakeCache.txt"; then
  rm -rf "${build_dir}"
fi

cmake -S "${repo_root}" -B "${build_dir}" -G Ninja \
  -DCMAKE_CXX_COMPILER="${CXX:-clang++}" \
  -DCMAKE_C_COMPILER="${CC:-clang}"
cmake --build "${build_dir}"
ctest --test-dir "${build_dir}" --output-on-failure
