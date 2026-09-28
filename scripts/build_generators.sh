#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
git submodule update --init third_party/NGen third_party/SGen
for generator in NGen SGen; do
  root="$repo_root/third_party/$generator"
  if [[ "$generator" == SGen ]]; then
    (cd "$root" && sbt 'regular:test' assembly)
  else
    (cd "$root" && sbt test assembly)
  fi
  name="${generator,,}"
  python3 - "$root" "$name" <<'PY'
import sys
from architecture_search.build_identity import verify
result = verify(sys.argv[1], generator=sys.argv[2])
print(f"{sys.argv[2]} source manifest: {'verified' if result['verified'] else result}")
if not result['verified']:
    raise SystemExit(1)
PY
done
