#!/usr/bin/env python3
"""Re-screen published N=512 NGen products with the SGen memory-collected pass."""
import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search.model import file_hash, run, write_json
from scripts.fhe512_sgen_precision import collected_counts


def inventory():
    matrix = ROOT/'docs/measured-evidence/fhe512-reduction-matrix.csv'
    covering = ROOT/'docs/measured-evidence/fhe512-covering-table.csv'
    candidates = list((ROOT/'build').glob('fhe512-*/ngen-*/q*/SearchTop.sv'))
    by_hash = {}
    for path in candidates:
        by_hash.setdefault(file_hash(path), []).append(path)
    points = {}
    with matrix.open(newline='') as stream:
        for row in csv.DictReader(stream):
            assert row['status'] == 'screened' and row['simulation_passed'] == 'True'
            assert row['error_bound'] == '0'
            name = (f"ngen-{row['backend']}-l{row['lanes']}-pe{row['pe'] or '1'}"
                    f"-r2-s1-{row['reduction']}-baseline"
                    + ('-switch' if row['boundary'] == 'switch' else '') + '-q0')
            matches = by_hash.get(row['rtl_sha256'], [])
            if not matches:
                raise ValueError(f'published matrix RTL missing: {name}')
            path = next((p for p in matches if '/q0/' in str(p)), matches[0])
            points[name] = dict(name=name, generator='ngen', rtl=str(path.relative_to(ROOT)),
                                rtl_sha256=row['rtl_sha256'], source='reduction-matrix',
                                max_abs_error=0, observed_max_abs_error=0,
                                latency_cycles=int(row['latency_cycles']),
                                initiation_interval_cycles=int(row['frame_interval_cycles']))
    results = json.loads((ROOT/'build/fhe512-covering/results.json').read_text())
    covering_results = {row['name']: row for row in results['points']}
    with covering.open(newline='') as stream:
        for row in csv.DictReader(stream):
            name = row['name']
            if name in points:
                continue  # The matrix uses the later verified NGen RTL for shared architectures.
            previous = covering_results[name]
            if row['simulation_passed'] != 'True' or previous.get('simulation_passed') is not True:
                raise ValueError(f'covering point lacks a passing product check: {name}')
            base, q = name.rsplit('-q', 1)
            path = ROOT/'build/fhe512-covering'/base/('q'+q)/'SearchTop.sv'
            if not path.is_file() or file_hash(path) != previous['rtl_sha256']:
                raise ValueError(f'covering RTL hash mismatch: {name}')
            points[name] = dict(name=name, generator='ngen', rtl=str(path.relative_to(ROOT)),
                                rtl_sha256=previous['rtl_sha256'], source='covering-grid',
                                max_abs_error=int(row['error_bound']),
                                observed_max_abs_error=int(row['observed_max_abs_error']),
                                latency_cycles=int(row['latency_cycles']),
                                initiation_interval_cycles=int(row['initiation_interval_cycles']))
    # The original covering-grid stage-parallel q4 RTL predates structural
    # lowering. Prefer its regenerated, independently simulated equivalent.
    refresh = ROOT/'build/fhe512-common-q4-refresh'
    refresh_results = refresh/'results.json'
    if refresh_results.is_file():
        for row in json.loads(refresh_results.read_text())['points']:
            name = row['name']
            if name != 'ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q4':
                continue
            path = refresh/'ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline/q4/SearchTop.sv'
            if row.get('simulation_passed') is not True or not path.is_file() or file_hash(path) != row['rtl_sha256']:
                raise ValueError('refreshed rounded stage-parallel RTL was not verified')
            old = points[name]
            if (row['max_abs_error'], row['latency_cycles'], row['initiation_interval_cycles']) != (
                    old['max_abs_error'], old['latency_cycles'], old['initiation_interval_cycles']):
                raise ValueError('refreshed rounded stage-parallel metrics changed')
            points[name] = dict(old, rtl=str(path.relative_to(ROOT)),
                                rtl_sha256=row['rtl_sha256'], source='refreshed-stage-q4')
    return [points[name] for name in sorted(points)]


def screen(point, out, timeout):
    rtl = ROOT/point['rtl']
    result = collected_counts(rtl.resolve(), out/point['name'], timeout)
    row = dict(point, synthesis_level=result['level'], yosys_sha256=result['yosys_sha256'],
               yosys_script_sha256=result['script_sha256'],
               yosys_netlist_sha256=result.get('netlist_sha256'),
               yosys_process=result['process'], passed=result['passed'])
    if result['rtl_sha256'] != point['rtl_sha256']:
        raise ValueError(f'RTL changed while screening: {point["name"]}')
    row.update(result.get('counts', {}))
    return row


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--timeout', type=int, default=1200)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--reuse-from', type=Path,
                   help='reuse screened rows from a prior campaign when RTL and tool hashes match')
    args = p.parse_args(argv)
    if args.workers < 1 or args.timeout < 1:
        p.error('workers and timeout must be positive')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    yosys = Path(os.environ.get('FHE512_YOSYS', ROOT/'build/tools/bin/yosys')).resolve()
    version = run([str(yosys), '-V'], out, out/'yosys.version.log', 30)
    if version['returncode'] or not (out/'yosys.version.log').read_text().startswith('Yosys 0.50 '):
        p.error('pinned Yosys 0.50 is required')
    points = inventory()
    manifest = dict(schema='fhe512-common-synth-manifest-v1', points=points,
                    image_sha256=os.environ.get('FHE512_IMAGE_SHA256'),
                    yosys_sha256=file_hash(yosys),
                    runner_sha256=file_hash(Path(__file__)),
                    common_pass_sha256=file_hash(ROOT/'scripts/fhe512_sgen_precision.py'),
                    covering_results_sha256=file_hash(ROOT/'build/fhe512-covering/results.json'),
                    source_evidence_sha256={name: file_hash(ROOT/'docs/measured-evidence'/name)
                        for name in ('fhe512-reduction-matrix.csv', 'fhe512-covering-table.csv')})
    if any(point['source'] == 'refreshed-stage-q4' for point in points):
        manifest['refreshed_q4_results_sha256'] = file_hash(
            ROOT/'build/fhe512-common-q4-refresh/results.json')
    if args.reuse_from:
        manifest['reuse_results_sha256'] = file_hash(args.reuse_from)
    manifest_path = out/'manifest.json'
    if args.resume:
        if not manifest_path.is_file() or json.loads(manifest_path.read_text()) != manifest:
            p.error('resume manifest differs; use a new output directory')
    elif manifest_path.exists():
        p.error('output directory already contains a campaign; use --resume')
    write_json(manifest_path, manifest)
    old_path = out/'results.json' if args.resume else args.reuse_from
    old_result = json.loads(old_path.read_text()) if old_path and old_path.is_file() else None
    if args.reuse_from and old_result is None:
        p.error('reuse source is missing')
    if old_result and (old_result['manifest']['image_sha256'] != manifest['image_sha256'] or
                       old_result['manifest']['yosys_sha256'] != manifest['yosys_sha256'] or
                       old_result['manifest']['common_pass_sha256'] != manifest['common_pass_sha256']):
        p.error('reuse source used a different image, Yosys binary, or synthesis pass')
    by_name = {row['name']: row for row in old_result['points'] if row.get('passed')} if old_result else {}
    rows = [by_name[point['name']] for point in points if point['name'] in by_name and
            by_name[point['name']]['rtl_sha256'] == point['rtl_sha256']]
    if args.reuse_from:
        for row in rows:
            (out/row['name']).symlink_to((args.reuse_from.resolve().parent/row['name']).resolve())
    remaining = [point for point in points if point['name'] not in {row['name'] for row in rows}]
    print(f'{len(points)} verified NGen points; {len(rows)} reused; {len(remaining)} to synthesize', flush=True)
    write_json(out/'results.json', dict(schema='fhe512-common-synth-v1',
                                        manifest=manifest, points=rows))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(screen, point, out, args.timeout): point for point in remaining}
        for future in as_completed(futures):
            point = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = dict(point, passed=False, error=repr(error))
            rows.append(row)
            rows.sort(key=lambda r: r['name'])
            write_json(out/'results.json', dict(schema='fhe512-common-synth-v1',
                                                manifest=manifest, points=rows))
            print(f"{len(rows)}/{len(points)} {point['name']}: "
                  f"{'screened' if row['passed'] else row.get('error', 'Yosys failed')}", flush=True)
    return 0 if len(rows) == len(points) and all(row['passed'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
