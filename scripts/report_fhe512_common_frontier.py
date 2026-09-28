#!/usr/bin/env python3
"""Build a same-pass NGen/SGen resource table and multidimensional frontier."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search.model import file_hash, write_json

OBJECTIVES = ('max_abs_error', 'cells', 'memory_bits', 'register_bits',
              'multipliers', 'latency_cycles', 'initiation_interval_cycles')


def frontier(points, error_limit=None):
    eligible = [point for point in points if point['passed'] and
                (error_limit is None or point['max_abs_error'] <= error_limit)]
    return [point['name'] for point in eligible if not any(
        all(other[key] <= point[key] for key in OBJECTIVES) and
        any(other[key] < point[key] for key in OBJECTIVES)
        for other in eligible if other is not point)]


def combine(ngen_path, sgen_path):
    ngen = json.loads(ngen_path.read_text())
    sgen = json.loads(sgen_path.read_text())
    nm = ngen['manifest']; sm = sgen['reference']
    if nm['image_sha256'] != sm['image_sha256'] or nm['yosys_sha256'] != sm['yosys_sha256']:
        raise ValueError('NGen and SGen used different image or Yosys binaries')
    if nm['common_pass_sha256'] != sm['source_sha256']['scripts/fhe512_sgen_precision.py']:
        raise ValueError('the memory-preserving Yosys pass changed')
    if sm['workload']['n'] != 512 or sm['workload']['modulus'] != 1 << 32:
        raise ValueError('unexpected SGen workload')
    points = []
    for row in ngen['points']:
        point = dict(name=row['name'], generator='ngen', source=row['source'],
                     rtl_sha256=row['rtl_sha256'], passed=row['passed'],
                     max_abs_error=row['max_abs_error'],
                     observed_max_abs_error=row['observed_max_abs_error'],
                     latency_cycles=row['latency_cycles'],
                     initiation_interval_cycles=row['initiation_interval_cycles'])
        if row['passed']:
            if row['synthesis_level'] != 'coarse-memory-collected':
                raise ValueError(f'wrong Yosys pass: {row["name"]}')
            point.update({key: row[key] for key in ('cells', 'memory_bits',
                         'register_bits', 'multipliers')})
        else:
            point['failure'] = row.get('error', row.get('yosys_process'))
        points.append(point)
    for row in sgen['points']:
        if row['fractional_bits'] == 24:
            continue  # Numerically uncertified control, retained in the SGen evidence.
        point = dict(name=row['name'], generator='sgen', source='sgen-precision',
                     rtl_sha256=row['rtl_sha256'], passed=row['status'] == 'screened',
                     max_abs_error=row['max_abs_error'],
                     observed_max_abs_error=row['observed_max_abs_error'],
                     latency_cycles=row['latency_cycles'],
                     initiation_interval_cycles=row['initiation_interval_cycles'])
        if point['passed']:
            point.update(cells=row['yosys_cells'], memory_bits=row['memory_bits'],
                         register_bits=row['register_bits'], multipliers=row['multipliers'])
        points.append(point)
    if len({point['name'] for point in points}) != len(points):
        raise ValueError('duplicate configuration names')
    return sorted(points, key=lambda point: point['name']), dict(
        ngen_manifest_sha256=file_hash(ngen_path.parent/'manifest.json'),
        ngen_results_sha256=file_hash(ngen_path), sgen_evidence_sha256=file_hash(sgen_path),
        image_sha256=nm['image_sha256'], yosys_sha256=nm['yosys_sha256'],
        common_pass_sha256=nm['common_pass_sha256'])


def markdown(points, fronts):
    by_name = {point['name']: point for point in points}
    lines = ['# N=512 common-pass NGen/SGen Pareto screening', '',
             f"{sum(p['passed'] for p in points)}/{len(points)} tested configurations completed "
             'the memory-collected Yosys 0.50 pass. All products have near-full-range signed '
             '32-bit inputs and outputs modulo 2^32.', '',
             'A point dominates another when it is no worse in all seven columns: '
             'analytical coefficient-error bound, generic cells, retained memory bits, '
             'register bits, multiplier operators, latency cycles, and frame interval cycles; '
             'and is strictly better in at least one. Smaller is better for every column. '
             'Products per 1,000 cycles equals 1,000 divided by frame interval, so it is '
             'not an independent objective. These resources are coarse Yosys estimates, '
             'not U280 utilization or a timing-qualified throughput.', '',
             f"Full frontier: **{len(fronts['all'])}** points; exact frontier: "
             f"**{len(fronts['exact'])}** points; error-at-most-8 frontier: "
             f"**{len(fronts['error_le_8'])}** points.", '',
             '## Full frontier', '',
             '| Configuration | Error bound | Cells | Memory bits | Register bits | Multipliers | '
             'Latency | Frame interval | Products / 1,000 cycles |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    def table_row(point):
        fmt = lambda key: f"{point[key]:,}" if point.get(key) is not None else '—'
        rate = 1000/point['initiation_interval_cycles'] if point.get('initiation_interval_cycles') else None
        return (f"| `{point['name']}` | {fmt('max_abs_error')} | {fmt('cells')} | "
                f"{fmt('memory_bits')} | {fmt('register_bits')} | {fmt('multipliers')} | "
                f"{fmt('latency_cycles')} | {fmt('initiation_interval_cycles')} | "
                f"{rate:.6f} |" if rate is not None else f"| `{point['name']}` | — | — | — | — | — | — | — | — |")
    for name in fronts['all']:
        lines.append(table_row(by_name[name]))
    lines += ['', '## All tested configurations', '',
              'Status `screened` means the existing RTL product check and this common Yosys '
              'pass both completed. The SGen 24-bit rejected control is listed in the '
              '[precision evidence](fhe512-sgen-precision.md), outside the eligible set.', '',
              '| Configuration | Error bound | Cells | Memory bits | Register bits | Multipliers | '
              'Latency | Frame interval | Products / 1,000 cycles | Status |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for point in points:
        lines.append(table_row(point) + f" {('screened' if point['passed'] else 'failed')} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngen-results', type=Path, required=True)
    p.add_argument('--sgen-evidence', type=Path, required=True)
    p.add_argument('--output-md', type=Path, required=True)
    p.add_argument('--output-csv', type=Path, required=True)
    p.add_argument('--evidence-file', type=Path, required=True)
    args = p.parse_args(argv)
    points, provenance = combine(args.ngen_results, args.sgen_evidence)
    fronts = dict(all=frontier(points), exact=frontier(points, 0),
                  error_le_8=frontier(points, 8))
    args.output_md.write_text(markdown(points, fronts))
    fields = ('name', 'generator', 'source', 'max_abs_error', 'observed_max_abs_error',
              'cells', 'memory_bits', 'register_bits', 'multipliers', 'latency_cycles',
              'initiation_interval_cycles', 'products_per_1000_cycles', 'full_frontier',
              'exact_frontier', 'passed', 'rtl_sha256')
    with args.output_csv.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for point in points:
            row = dict(point)
            row['products_per_1000_cycles'] = (1000/point['initiation_interval_cycles']
                 if point.get('initiation_interval_cycles') else None)
            row['full_frontier'] = point['name'] in fronts['all']
            row['exact_frontier'] = point['name'] in fronts['exact']
            writer.writerow({key: row.get(key) for key in fields})
    write_json(args.evidence_file, dict(schema='fhe512-common-frontier-v1',
                                        objectives=OBJECTIVES, provenance=provenance,
                                        points=points, frontiers=fronts))
    print(f"{len(points)} points, {len(fronts['all'])} on the full frontier", flush=True)


if __name__ == '__main__':
    main()
