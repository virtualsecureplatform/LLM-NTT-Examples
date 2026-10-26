#!/usr/bin/env bash
# Qualify the 16-point width/PE grid, then map and route two wider finalists.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
qualification=build/polynomial-study-512-wide-ntt
physical=build/device-polynomial-512-wide-ntt
mode="${1:-run}"
if [[ "$mode" != run && "$mode" != resume && "$mode" != wait ]]; then
  echo 'Usage: scripts/run_wide_ntt_study.sh [run|resume|wait]' >&2
  exit 2
fi
mapfile -t names < <(python3 - <<'PY'
import json
from scripts.polynomial_study import enumerate_points
for row in enumerate_points(json.load(open('studies/torus512-wide-ntt.json'))):
    c=row['configuration']
    if row['status']=='pending' and c['generator']=='ngen' and c['reduction']=='montgomery':
        print(row['name'])
PY
)
if [[ ${#names[@]} != 16 ]]; then
  echo 'Expected exactly sixteen registered Montgomery NTT configurations' >&2
  exit 2
fi
if [[ "$mode" == wait ]]; then
  # Attach only to the already-running qualification campaign, without writing it.
  python3 - "$qualification/results.json" "${names[@]}" <<'PY'
import json,sys,time
from pathlib import Path
path=Path(sys.argv[1]);wanted=set(sys.argv[2:])
deadline=time.monotonic()+16*3600+600
while time.monotonic()<deadline:
    if path.is_file():
        try:
            rows={r['name']:r for r in json.loads(path.read_text())['points']}
            if wanted<=rows.keys() and all(rows[n]['status']!='pending' for n in wanted):
                break
        except json.JSONDecodeError:
            pass
    time.sleep(15)
else:
    raise SystemExit('Qualification did not finish before the campaign deadline')
PY
else
  resume=()
  if [[ "$mode" == resume ]]; then resume=(--resume); fi
  scripts/run_polynomial_study.sh --spec studies/torus512-wide-ntt.json \
    --output-dir "$qualification" --configuration-names "${names[@]}" "${resume[@]}"
fi
# Promote the fastest wider point and a smaller-resource wider alternative.
mapfile -t finalists < <(python3 - "$qualification/results.json" <<'PY'
import json,sys
rows=[r for r in json.load(open(sys.argv[1]))['points'] if r.get('passed')
      and r['configuration']['generator']=='ngen' and r['configuration']['lanes']>=8]
if not rows:
    raise SystemExit('No wider NTT passed qualification')
fast=min(rows,key=lambda r:(r['initiation_interval_cycles'],r['yosys_cells'],r['name']))
other=[r for r in rows if r['name']!=fast['name']]
selected=[fast]
if other:selected.append(min(other,key=lambda r:(r['yosys_cells'],r['initiation_interval_cycles'],r['name'])))
for row in selected:print(row['name'])
PY
)
if [[ ${#finalists[@]} == 0 ]]; then
  echo 'No qualified wider finalists; inspect qualification results' >&2
  exit 1
fi
selection=()
for name in "${finalists[@]}"; do selection+=(--configuration-name "$name"); done
resume=()
if [[ -f "$physical/manifest.json" ]]; then resume=(--resume); fi
python3 scripts/device_polynomial_study.py --campaign "$qualification" \
  --target studies/u280-kernel-harness.json --output-dir "$physical" \
  --policy enumerate --max-trials "${#finalists[@]}" \
  --route-budget "${#finalists[@]}" --max-route-budget "${#finalists[@]}" \
  --timeout 3600 --threads 4 "${selection[@]}" "${resume[@]}"
echo "Qualification results: $qualification/summary.md"
echo "Physical results: $physical/summary.md"
