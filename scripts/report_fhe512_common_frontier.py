#!/usr/bin/env python3
"""Build a same-pass NGen/SGen resource table and multidimensional frontier."""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search.model import file_hash, write_json

OBJECTIVES = ('max_abs_error', 'cells', 'memory_bits', 'register_bits',
              'multipliers', 'latency_cycles', 'initiation_interval_cycles')
AXES = ('backend', 'lanes', 'pe', 'radix', 'stage_groups', 'reduction',
        'profile', 'boundary', 'output_quant_bits', 'fractional_bits',
        'guard_bits', 'omit_low_diagonals')
NGEN_NAME = re.compile(
    r'ngen-(streamed|stage-parallel)-l(\d+)-pe(\d+)-r(\d+)-s(\d+)'
    r'-(barrett|montgomery|shoup)-(baseline|f300)(-switch)?-q(\d+)')
SGEN_NAME = re.compile(r'sgen-(compact|full-throughput)-l(\d+)-f(\d+)-g(\d+)(?:-omit(\d+))?')


def configuration_axes(name):
    """Expose every encoded search control as a typed evidence field."""
    ngen = NGEN_NAME.fullmatch(name)
    if ngen:
        backend, lanes, pe, radix, groups, reduction, profile, switch, quant = ngen.groups()
        return dict(backend=backend, lanes=int(lanes), pe=int(pe), radix=int(radix),
                    stage_groups=int(groups), reduction=reduction, profile=profile,
                    boundary='switch' if switch else 'indexed', output_quant_bits=int(quant),
                    fractional_bits=None, guard_bits=None, omit_low_diagonals=None)
    sgen = SGEN_NAME.fullmatch(name)
    if sgen:
        backend, lanes, fractional, guard, omitted = sgen.groups()
        return dict(backend=backend, lanes=int(lanes), pe=None, radix=None,
                    stage_groups=None, reduction=None, profile=None, boundary=None,
                    output_quant_bits=None, fractional_bits=int(fractional),
                    guard_bits=int(guard), omit_low_diagonals=int(omitted or 0))
    raise ValueError(f'unrecognized configuration name: {name}')


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
        point.update(configuration_axes(row['name']))
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
        point.update(configuration_axes(row['name']))
        if (point['fractional_bits'], point['omit_low_diagonals']) != (
                row['fractional_bits'], row['omit_low_diagonals']):
            raise ValueError(f'SGen control fields disagree: {row["name"]}')
        if point['passed']:
            point.update(cells=row['yosys_cells'], memory_bits=row['memory_bits'],
                         register_bits=row['register_bits'], multipliers=row['multipliers'])
        points.append(point)
    if len({point['name'] for point in points}) != len(points):
        raise ValueError('duplicate configuration names')
    points.sort(key=lambda point: point['name'])
    for generator, prefix in (('ngen', 'N'), ('sgen', 'S')):
        for index, point in enumerate((p for p in points if p['generator'] == generator), 1):
            point['id'] = f'{prefix}{index:02d}'
    return points, dict(
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
             'Configuration controls are separate columns. The short ID links each row '
             'to the full RTL name and hash in the CSV and JSON evidence. A dash means '
             'the control does not apply to that generator.', '',
             '## Full frontier', '']

    def table(rows, generator, include_status=False):
        if generator == 'ngen':
            controls = [('id', 'ID'), ('backend', 'Backend'), ('lanes', 'Lanes'),
                        ('pe', 'PE'), ('radix', 'Radix'), ('stage_groups', 'Stage groups'),
                        ('reduction', 'Reduction'), ('profile', 'Profile'),
                        ('boundary', 'Boundary'), ('output_quant_bits', 'Output round bits')]
        else:
            controls = [('id', 'ID'), ('backend', 'Backend'), ('lanes', 'Lanes'),
                        ('fractional_bits', 'FFT fractional bits'), ('guard_bits', 'Guard bits'),
                        ('omit_low_diagonals', 'Omitted diagonals')]
        metrics = [('max_abs_error', 'Error bound'), ('cells', 'Cells'),
                   ('memory_bits', 'Memory bits'), ('register_bits', 'Register bits'),
                   ('multipliers', 'Multipliers'), ('latency_cycles', 'Latency'),
                   ('initiation_interval_cycles', 'Frame interval')]
        headers = [label for _, label in controls + metrics] + ['Products / 1,000 cycles']
        if include_status:
            headers.append('Status')
        result = ['| ' + ' | '.join(headers) + ' |',
                  '| ' + ' | '.join('---' if i == 0 or header in (
                      'Backend', 'Reduction', 'Profile', 'Boundary', 'Status') else '---:'
                      for i, header in enumerate(headers)) + ' |']
        for point in rows:
            values = []
            for key, _ in controls + metrics:
                value = point.get(key)
                values.append(f'{value:,}' if isinstance(value, int) else value or '—')
            interval = point.get('initiation_interval_cycles')
            values.append(f'{1000/interval:.6f}' if interval else '—')
            if include_status:
                values.append('screened' if point['passed'] else 'failed')
            result.append('| ' + ' | '.join(values) + ' |')
        return result

    frontier_points = [by_name[name] for name in fronts['all']]
    for generator, label in (('ngen', 'NGen'), ('sgen', 'SGen')):
        lines += [f'### {label}', '']
        lines += table([point for point in frontier_points if point['generator'] == generator],
                       generator)
        lines.append('')
    lines += ['', '## All tested configurations', '',
              'Status `screened` means the existing RTL product check and this common Yosys '
              'pass both completed. The SGen 24-bit rejected control is listed in the '
              '[precision evidence](fhe512-sgen-precision.md), outside the eligible set.', '']
    for generator, label in (('ngen', 'NGen'), ('sgen', 'SGen')):
        lines += [f'### {label}', '']
        lines += table([point for point in points if point['generator'] == generator],
                       generator, include_status=True)
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


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
    fields = ('id', 'generator') + AXES + ('max_abs_error', 'observed_max_abs_error',
              'cells', 'memory_bits', 'register_bits', 'multipliers', 'latency_cycles',
              'initiation_interval_cycles', 'products_per_1000_cycles', 'full_frontier',
              'exact_frontier', 'passed', 'source', 'name', 'rtl_sha256')
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
    write_json(args.evidence_file, dict(schema='fhe512-common-frontier-v2',
                                        objectives=OBJECTIVES, provenance=provenance,
                                        points=points, frontiers=fronts))
    print(f"{len(points)} points, {len(fronts['all'])} on the full frontier", flush=True)


if __name__ == '__main__':
    main()
