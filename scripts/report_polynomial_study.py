#!/usr/bin/env python3
"""Export readable tables and compact CSV snapshots from measured studies."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


METRICS = ('max_abs_error', 'observed_max_abs_error', 'yosys_cells',
           'memory_bits', 'register_bits', 'multipliers',
           'latency_cycles', 'initiation_interval_cycles')


def design(row):
    c = row.get('configuration', {})
    if not c:
        return row.get('dependency', 'unresolved')
    if c['generator'] == 'sgen':
        name = f"FFT {c['backend']}, L{c['lanes']}, f{c['fractional_bits']}, g{c.get('guard_bits', 0)}, omit{c.get('omit_low_diagonals', 0)}"
    else:
        name = f"NTT {c['backend']}, L{c['lanes']}, R{c['radix']}, G{c['stage_groups']}, {c['reduction']}"
        if 'pe' in c:
            name += f", PE{c['pe']}"
    if row['quant_bits']:
        name += f", round{row['quant_bits']}"
    return name


def table(rows, frontier):
    lines = ['| Design | Error bound | Observed max error | Cells | Memory bits | Register bits | Multiplier operators | Latency cycles | Interval cycles | Pareto |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for r in rows:
        values = [design(r), *(f'{r[k]:,}' for k in METRICS),
                  'yes' if r['name'] in frontier else 'no']
        lines.append('| ' + ' | '.join(values) + ' |')
    return lines


def combined_campaigns(campaigns):
    groups, provenance = {}, []
    objectives = [k for k in METRICS if k != 'observed_max_abs_error']
    for folder in campaigns:
        source = folder / 'results.json'
        data = json.loads(source.read_text())
        manifest = json.loads((folder / 'manifest.json').read_text())
        n = manifest['spec']['n']
        group = groups.setdefault(n, dict(points={}, corpora={}, contracts={}, limits={0}))
        for name, digest in manifest['corpora'].items():
            if name in group['corpora'] and group['corpora'][name] != digest:
                raise ValueError('cannot merge different corpora for ' + name)
            group['corpora'][name] = digest
        group['limits'].update(manifest['spec']['error_limits'])
        for row in data['points']:
            workload = row['workload_name']
            if workload in group['contracts'] and group['contracts'][workload] != row['workload']:
                raise ValueError('cannot merge different contracts for ' + workload)
            group['contracts'][workload] = row['workload']
            old = group['points'].get(row['name'])
            if old and old.get('passed') and row.get('passed'):
                if any(old[k] != row[k] for k in METRICS):
                    raise ValueError('conflicting duplicate measurements for ' + row['name'])
            if old is None or not old.get('passed'):
                group['points'][row['name']] = row
        provenance.append(dict(n=n, campaign=folder.name,
                               results_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                               manifest_sha256=hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest(),
                               spec=manifest['spec'], corpus_sha256=manifest['corpora'],
                               coverage=data['coverage'], frontiers=data['frontiers']))
    combined = []
    for n, group in groups.items():
        rows = list(group['points'].values())
        frontiers = {}
        for workload in group['contracts']:
            frontiers[workload] = {}
            for limit in [None, *sorted(group['limits'])]:
                eligible = [r for r in rows if r['workload_name'] == workload and r.get('passed')
                            and (limit is None or r['max_abs_error'] <= limit)]
                frontiers[workload][str(limit)] = [r['name'] for r in eligible if not any(
                    all(s[k] <= r[k] for k in objectives) and any(s[k] < r[k] for k in objectives)
                    for s in eligible)]
        combined.append((n, dict(points=rows, frontiers=frontiers)))
    return combined, provenance


def export(campaigns, output):
    output.mkdir(parents=True, exist_ok=True)
    lines = ['# Achieved polynomial multiplication design space', '',
             'Measured negacyclic products modulo `2^32`, with fresh operands and a two-coefficient ready/valid interface. '
             'Full operands are signed 32-bit, byte operands are in [-128, 127], and ternary operands are in [-1, 1].', '',
             'Cells and multiplier operators are coarse Yosys counts with inferred memories retained; they are not FPGA LUTs or DSP counts. '
             'Latency and interval are measured in cycles; interval is the spacing between products in an uninterrupted 12-frame run. '
             'No clock frequency or physical implementation is assumed. Error bounds are analytical; observed errors cover the 101-frame corpus and do not establish FHE decryption reliability.', '',
             'Pareto membership uses all seven objectives: error bound, cells, memory bits, register bits, multiplier operators, latency, and interval. '
             'It is computed separately for each workload over qualified points. Certification rejections and timeouts are excluded. '
             'L = internal lanes, R = radix, G = stage groups, PE = processing elements, f = fractional bits, g = guard bits, omit = omitted low digit diagonals, and round = output rounding bits.', '']
    combined, provenance = combined_campaigns(campaigns)
    for n, data in combined:
        rows = data['points']
        label = f'torus{n}'
        csv_name = label + '-points.csv'
        fields = ['name', 'workload_name', 'status', 'reason', 'design', 'quant_bits',
                  *METRICS, 'prime_count', 'digit_products', 'rtl_sha256', 'pareto', 'configuration_json']
        with (output / csv_name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fields, extrasaction='ignore', lineterminator='\n')
            writer.writeheader()
            for r in rows:
                frontier = data['frontiers'][r['workload_name']]['None']
                writer.writerow({**r, 'design': design(r), 'pareto': r['name'] in frontier,
                                 'configuration_json': json.dumps(r.get('configuration', {}), sort_keys=True)})
        lines += [f'## N={n}', '', f'All requested points, readable designs, status, point IDs, and metrics: [{csv_name}]({csv_name}).', '',
                  f'![N={n} cell count versus cycles per product]({label}-resource-throughput.svg)', '',
                  'Both axes use logarithmic scales. Overlapping points are retained without jitter. '
                  'Black rings mark the seven-objective Pareto points; this is a projection, so they need not form a two-dimensional frontier. '
                  f'[PNG]({label}-resource-throughput.png) · [SVG]({label}-resource-throughput.svg)', '',
                  '| Workload | Qualified | Certificate rejected | Timeout | Unsupported | Pending | Other |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        for workload in sorted(data['frontiers']):
            counts = Counter(r['status'] for r in rows if r['workload_name'] == workload)
            statuses = ('screened', 'certificate-rejected', 'timeout', 'unsupported', 'pending')
            other = sum(v for k,v in counts.items() if k not in statuses)
            lines.append('| ' + ' | '.join([workload, *(str(counts[k]) for k in statuses), str(other)]) + ' |')
        for workload, views in sorted(data['frontiers'].items()):
            good = [r for r in rows if r.get('passed') and r['workload_name'] == workload]
            exact = [r for r in good if r['max_abs_error'] == 0]
            lines += ['', f'### {workload}', '']
            if n <= 32:
                selected = good
                lines += ['All qualified demo configurations:', '']
            else:
                selected = []
                if exact:
                    for metric in ('yosys_cells', 'initiation_interval_cycles'):
                        selected.append(min(exact, key=lambda r: (r[metric], r['yosys_cells'], r['memory_bits'], r['name'])))
                fft = [r for r in good if r['configuration']['generator'] == 'sgen' and not r['quant_bits']]
                fft_groups = {}
                for r in fft:
                    c = r['configuration']
                    fft_groups.setdefault((c['backend'], c['lanes'], c['guard_bits']), []).append(r)
                for group in fft_groups.values():
                    precision = min(r['configuration']['fractional_bits'] for r in group)
                    selected += [r for r in group if r['configuration']['fractional_bits'] == precision]
                selected = list({r['name']: r for r in selected}.values())
                lines += ['Representative designs: minimum-cell exact, minimum-interval exact '
                          '(ties use cells, memory, then point ID), and the lowest qualified FFT precision for each backend/lane/guard combination with its omission variants. '
                          'These single-objective selections are not unique overall winners.', '']
            lines += table(selected, views['None'])
            if n > 32:
                lines += ['', '<details>', '<summary>All Pareto designs across error levels</summary>', '']
                lines += table([r for r in good if r['name'] in views['None']], views['None'])
                lines += ['', '</details>']
        timeouts = [r for r in rows if r['status'] == 'timeout']
        if timeouts:
            lines += ['', 'Timeouts (measurement incomplete; not an arithmetic failure):', '',
                      '| Workload | Design | Stage |', '| --- | --- | --- |']
            lines += [f"| {r['workload_name']} | {design(r)} | {r.get('reason', 'unknown')} |" for r in timeouts]
        if n == 512:
            lines += ['', '### FFT error / throughput tradeoff', '',
                      '![N=512 FFT error bound versus cycles per product](torus512-error-throughput.svg)', '',
                      'The horizontal scale is symmetric logarithmic so exact (zero-error) products remain visible. '
                      'Each curve fixes FFT backend, lanes, guard bits, and fractional precision at 30, then varies omission depth. '
                      'Bounds apply to the polynomial product contract; observed maxima are listed in the tables. '
                      '[PNG](torus512-error-throughput.png) · [SVG](torus512-error-throughput.svg)']
        lines += ['']
    lines += ['Source result/manifest hashes, workload specifications, corpus hashes, coverage, and frontier IDs are pinned in [provenance.json](provenance.json). '
              'Detailed simulator and synthesis evidence remains in the local campaign directories; these CSVs are compact result snapshots.', '']
    (output / 'polynomial-results.md').write_text('\n'.join(lines))
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, action='append', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    export(args.campaign, args.output_dir)
