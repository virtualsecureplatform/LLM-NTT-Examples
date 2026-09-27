#!/usr/bin/env python3
"""Compare exact N=512 reduction and boundary-transpose configurations."""
import argparse
import csv
import json
from pathlib import Path


def expected(reductions):
    points = set()
    for backend in ('streamed', 'stage-parallel'):
        for lanes in (2, 4):
            for reduction in reductions:
                pe_values = (1, 2) if backend == 'streamed' and reduction == 'barrett' else (
                    (1,) if backend == 'streamed' else (None,))
                for pe in pe_values:
                    for transpose in ('indexed', 'switch'):
                        points.add((backend, lanes, pe, reduction, transpose))
    return points


def rows(paths, prefer_later=False, reductions=('barrett',)):
    wanted = expected(reductions)
    found = {}
    for path in paths:
        evidence = json.loads(path.read_text())
        workload = evidence['workload']
        if (workload['n'] != 512 or workload['ring'] != 'negacyclic' or workload['modulus'] != 1 << 32
                or workload['a_range'] != [-2147483647, 2147483647]
                or workload['b_range'] != [-2147483647, 2147483647]):
            raise ValueError(f'incompatible workload in {path}')
        for point in evidence['points']:
            c = point['configuration']
            if (c['backend'] not in ('streamed', 'stage-parallel') or c['radix'] != 2
                    or c['stage_groups'] != 1 or c['reduction'] not in reductions
                    or c['profile'] != 'baseline' or point['quant_bits'] != 0):
                continue
            key = (c['backend'], c['lanes'], c.get('pe') if c['backend'] == 'streamed' else None,
                   c['reduction'], c.get('transpose', 'indexed'))
            if key not in wanted:
                continue
            if key in found and not prefer_later:
                raise ValueError(f'duplicate configuration {key}')
            if not point['simulation_passed']:
                status = 'simulation failed'
            elif point['yosys_passed']:
                status = 'screened'
            elif point.get('yosys_timed_out'):
                elapsed_minutes = round(point['yosys_seconds'] / 60)
                status = f'Yosys timeout (~{elapsed_minutes * 60}s)'
            elif point.get('yosys_returncode') == -15:
                status = 'Yosys budget stop'
            else:
                status = 'Yosys failed'
            found[key] = dict(backend=c['backend'], lanes=c['lanes'], pe=c.get('pe') if c['backend'] == 'streamed' else None,
                              reduction=c['reduction'], boundary=key[4], error_bound=point['max_abs_error'],
                              observed_error=point['observed_max_abs_error'], yosys_cells=point['yosys_cells'],
                              latency_cycles=point['latency_cycles'], frame_interval_cycles=point['initiation_interval_cycles'],
                              products_per_1000_cycles=point['throughput_products_per_1000_cycles'],
                              simulation_passed=point['simulation_passed'], status=status,
                              rtl_sha256=point['rtl_sha256'])
    if set(found) != wanted:
        raise ValueError(f'missing configurations: {sorted(wanted - set(found), key=str)}')
    return [found[key] for key in sorted(wanted, key=lambda x: (x[0] != 'streamed', x[1], x[2] or 0,
                                                                x[3], x[4] != 'indexed'))]


def markdown(points):
    reductions = sorted({p['reduction'] for p in points})
    reduction_text = '/'.join(name.title() for name in reductions)
    reduction_text += ' reduction' if len(reductions) == 1 else ' reductions'
    lines = ['# N=512 reduction and boundary-transpose comparison' if len(reductions) > 1
             else '# N=512 boundary-transpose comparison', '',
             'All rows are exact 32-bit-torus negacyclic polynomial products with radix 2, '
             f'{reduction_text}, baseline profile, and one stage group. '
             f"{sum(p['simulation_passed'] for p in points)}/{len(points)} rows passed "
             'the 12-frame RTL product check. `—` means Yosys did not produce a cell count. '
             'Cells are coarse Yosys operators after memory lowering, not U280 LUTs; '
             'throughput is products per 1,000 cycles without an assumed clock.', '',
             '| Backend | Lanes | PE | Reduction | Boundary | Error bound | Observed error | Yosys cells | '
             'Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |',
             '| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for p in points:
        f = lambda value: f'{value:,}' if isinstance(value, int) else '—'
        rate = p['products_per_1000_cycles']
        formatted_rate = f'{rate:.3f}' if rate is not None else '—'
        lines.append(f"| {p['backend']} | {p['lanes']} | {f(p['pe'])} | {p['reduction']} | {p['boundary']} | "
                     f"{f(p['error_bound'])} | {f(p['observed_error'])} | {f(p['yosys_cells'])} | "
                     f"{f(p['latency_cycles'])} | {f(p['frame_interval_cycles'])} | "
                     f"{formatted_rate} | {p['status']} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path, nargs='+')
    parser.add_argument('--prefer-later', action='store_true',
                        help='replace duplicate configurations with later evidence files')
    parser.add_argument('--reductions', nargs='+', choices=('barrett', 'montgomery', 'shoup'),
                        default=['barrett'], help='reduction algorithms required in the matrix')
    parser.add_argument('--output-md', type=Path, required=True)
    parser.add_argument('--output-csv', type=Path, required=True)
    args = parser.parse_args()
    points = rows(args.evidence, prefer_later=args.prefer_later, reductions=args.reductions)
    args.output_md.write_text(markdown(points))
    with args.output_csv.open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(points[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(points)
    print(f'{len(points)} configurations: {args.output_md}')


if __name__ == '__main__':
    main()
