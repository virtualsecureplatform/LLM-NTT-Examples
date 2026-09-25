#!/usr/bin/env python3
"""Summarize a completed pre-route covering grid without vendor implementation."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search.model import file_hash, write_json
from scripts.fhe512_preroute import configuration_name, pareto, quantization_points


def summarize(result, directory):
    manifest = result['manifest']; points = result['points']; grid = manifest['grid']
    planned = sum(quantization_points(c, bits, grid)
                  for c in manifest['configurations'] for bits in manifest['quant_bits'])
    checked = []
    for point in points:
        if 'quant_bits' not in point:
            checked.append(False)
            continue
        name = configuration_name(point['configuration']); bits = point['quant_bits']
        path = directory/name/('q'+str(bits))/'SearchTop.sv'
        checked.append(path.is_file() and file_hash(path) == point['rtl_sha256'])
    passed = [p for p in points if p.get('passed')]
    exact = [p for p in passed if p['max_abs_error'] == 0]
    frontier = pareto(points)
    if result['frontier'] != frontier:
        raise ValueError('saved frontier differs from measured records')
    if any(name not in {x['name'] for x in points} for name in frontier):
        raise ValueError('frontier refers to a missing point')
    summary = dict(schema='fhe512-preroute-summary-v1', grid=grid, planned_points=planned,
                   planned_architectures=len(manifest['configurations']),
                   recorded_points=len(points), passed_points=len(passed), failed_points=len(points)-len(passed),
                   simulation_passed=sum(p.get('simulation_passed') is True for p in points),
                   yosys_passed=sum(p.get('yosys_passed') is True for p in points),
                   verified_rtl_hashes=sum(checked), unique_rtl_hashes=len({p['rtl_sha256'] for p in passed}),
                   exact_points=len(exact), frontier=frontier,
                   complete=len(points) == planned and all(checked),
                   image_sha256=manifest.get('image_sha256'),
                   yosys_sha256=manifest['tools']['yosys']['sha256'])
    summary['axis_values'] = {key: sorted({str(c.get(key, 'indexed' if key == 'transpose' else 'n/a'))
                                            for c in manifest['configurations']})
                              for key in ('backend', 'lanes', 'pe', 'radix', 'stage_groups', 'reduction', 'profile', 'transpose')}
    return summary


def point_status(point, directory):
    if point.get('passed'):
        return 'screened'
    if point.get('reason'):
        return point['reason']
    if 'quant_bits' not in point:
        return 'generation failed'
    path = directory/configuration_name(point['configuration'])/('q'+str(point['quant_bits']))/'yosys'/'result.json'
    evidence = json.loads(path.read_text()) if path.is_file() else {}
    process = evidence.get('process', {})
    if process.get('timed_out'):
        return 'Yosys timeout'
    if process.get('returncode') == -15:
        return 'Yosys budget stop'
    if not point.get('simulation_passed'):
        return 'simulation failed'
    if not point.get('yosys_passed'):
        return 'Yosys failed'
    return 'error limit exceeded'


def metric_rows(result, directory):
    for point in result['points']:
        c = point['configuration']
        yield dict(name=point['name'], backend=c['backend'], transpose=c.get('transpose', 'indexed'), lanes=c['lanes'],
                   pe=c.get('pe', 1), radix=c['radix'], stage_groups=c['stage_groups'],
                   reduction=c['reduction'], profile=c['profile'], quant_bits=point.get('quant_bits'),
                   error_bound=point.get('max_abs_error'),
                   observed_max_abs_error=point.get('observed_max_abs_error'),
                   yosys_cells=point.get('yosys_cells'), latency_cycles=point.get('latency_cycles'),
                   initiation_interval_cycles=point.get('initiation_interval_cycles'),
                   throughput_products_per_1000_cycles=point.get('throughput_products_per_1000_cycles'),
                   simulation_passed=point.get('simulation_passed'),
                   yosys_passed=point.get('yosys_passed'), status=point_status(point, directory))


def markdown(result, summary, directory):
    by_name = {p['name']: p for p in result['points']}
    lines = [f"# N={result['manifest']['workload']['n']} pre-route screening", '',
             f"Grid: `{summary['grid']}`; {summary['planned_architectures']} architectures; "
             f"{summary['passed_points']}/{summary['planned_points']} planned points completed Yosys screening; "
             f"{summary['unique_rtl_hashes']} unique RTL hashes among passed points.", '',
             'Covered axes: '+', '.join(f"{key}={{{', '.join(values)}}}" for key, values in summary['axis_values'].items())+'.', '',
             'The cell counts are coarse Yosys operators after memory lowering, not U280 LUTs. '
             'Throughput is products per 1,000 cycles; no achieved clock or routed throughput is inferred.', '',
             '| Frontier point | Error bound | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name in summary['frontier']:
        p = by_name[name]
        lines.append(f"| `{name}` | {p['max_abs_error']} | {p['yosys_cells']:,} | "
                     f"{p['latency_cycles']:,} | {p['initiation_interval_cycles']:,} | "
                     f"{p['throughput_products_per_1000_cycles']:.3f} |")
    lines += ['', '## All evaluated configurations', '',
              'Each row is one complete N=512 polynomial product. `q4` rounds output to multiples '
              'of 16; all other points are exact (`q0`). `—` means no Yosys cell result. '
              f"{summary['simulation_passed']}/{summary['recorded_points']} points passed RTL simulation. "
              'A point is resource-qualified only when '
              'its status is `screened`.', '',
              '| Configuration | Error bound | Observed error | Yosys cells | Latency cycles | '
              'Frame interval cycles | Products / 1,000 cycles | Status |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for row in metric_rows(result, directory):
        fmt = lambda value: f'{value:,}' if isinstance(value, int) else '—'
        rate = row['throughput_products_per_1000_cycles']
        formatted_rate = f'{rate:.3f}' if rate is not None else '—'
        lines.append(f"| `{row['name']}` | {fmt(row['error_bound'])} | "
                     f"{fmt(row['observed_max_abs_error'])} | {fmt(row['yosys_cells'])} | "
                     f"{fmt(row['latency_cycles'])} | {fmt(row['initiation_interval_cycles'])} | "
                     f"{formatted_rate} | {row['status']} |")
    failures = [p for p in result['points'] if not p.get('passed')]
    lines += ['', f"Points without complete screening: {len(failures)}."]
    for p in failures:
        lines.append(f"- `{p['name']}`: {point_status(p, directory)}")
    return '\n'.join(lines)+'\n'


def evidence_snapshot(result, summary, directory, existing_schema=None):
    keep = ('name', 'configuration', 'quant_bits', 'max_abs_error', 'observed_max_abs_error',
            'yosys_cells', 'latency_cycles', 'initiation_interval_cycles',
            'throughput_products_per_1000_cycles', 'simulation_passed', 'yosys_passed',
            'passed', 'rtl_sha256')
    points = []
    for point in result['points']:
        row = {key: point[key] for key in keep if key in point}
        if 'quant_bits' in point:
            path = directory/configuration_name(point['configuration'])/('q'+str(point['quant_bits']))/'yosys'/'result.json'
            if path.is_file():
                process = json.loads(path.read_text()).get('process', {})
                row.update(yosys_returncode=process.get('returncode'),
                           yosys_timed_out=process.get('timed_out'),
                           yosys_seconds=process.get('seconds'))
        points.append(row)
    return dict(schema=existing_schema or 'fhe512-preroute-evidence-v1',
                workload=result['manifest']['workload'], summary=summary, points=points,
                limitation=result.get('limitations',
                                      'Yosys generic cells and cycle counts only; no U280 resources or clock'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--evidence-file', type=Path,
                        help='write a compact, reproducible snapshot of every measured point')
    args = parser.parse_args(argv); directory = args.output_dir.resolve()
    result = json.loads((directory/'results.json').read_text())
    summary = summarize(result, directory)
    write_json(directory/'summary.json', summary)
    (directory/'summary.md').write_text(markdown(result, summary, directory))
    rows = list(metric_rows(result, directory))
    with (directory/'all-points.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]) if rows else ['name'],
                                lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    if args.evidence_file:
        existing = json.loads(args.evidence_file.read_text()) if args.evidence_file.is_file() else {}
        write_json(args.evidence_file, evidence_snapshot(result, summary, directory,
                                                       existing.get('schema')))
    print(directory/'summary.md')
    return 0 if summary['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
