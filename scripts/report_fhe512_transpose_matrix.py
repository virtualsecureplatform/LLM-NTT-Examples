#!/usr/bin/env python3
"""Compare the exact N=512 indexed and switch boundary configurations."""
import argparse
import csv
import json
from pathlib import Path


EXPECTED = {(backend, lanes, pe, transpose)
            for backend in ('streamed', 'stage-parallel')
            for lanes in (2, 4)
            for pe in ((1, 2) if backend == 'streamed' else (None,))
            for transpose in ('indexed', 'switch')}


def rows(paths):
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
                    or c['stage_groups'] != 1 or c['reduction'] != 'barrett'
                    or c['profile'] != 'baseline' or point['quant_bits'] != 0):
                continue
            key = (c['backend'], c['lanes'], c.get('pe') if c['backend'] == 'streamed' else None,
                   c.get('transpose', 'indexed'))
            if key not in EXPECTED:
                continue
            if key in found:
                raise ValueError(f'duplicate configuration {key}')
            if not point['simulation_passed']:
                status = 'simulation failed'
            elif point['yosys_passed']:
                status = 'screened'
            elif point.get('yosys_timed_out'):
                status = f"Yosys timeout ({point['yosys_seconds']:.0f}s)"
            elif point.get('yosys_returncode') == -15:
                status = 'Yosys budget stop'
            else:
                status = 'Yosys failed'
            found[key] = dict(backend=c['backend'], lanes=c['lanes'], pe=c.get('pe') if c['backend'] == 'streamed' else None,
                              boundary=key[3], error_bound=point['max_abs_error'],
                              observed_error=point['observed_max_abs_error'], yosys_cells=point['yosys_cells'],
                              latency_cycles=point['latency_cycles'], frame_interval_cycles=point['initiation_interval_cycles'],
                              products_per_1000_cycles=point['throughput_products_per_1000_cycles'],
                              simulation_passed=point['simulation_passed'], status=status,
                              rtl_sha256=point['rtl_sha256'])
    if set(found) != EXPECTED:
        raise ValueError(f'missing configurations: {sorted(EXPECTED - set(found), key=str)}')
    return [found[key] for key in sorted(EXPECTED, key=lambda x: (x[0] != 'streamed', x[1], x[2] or 0,
                                                                  x[3] != 'indexed'))]


def markdown(points):
    lines = ['# N=512 boundary-transpose comparison', '',
             'All rows are exact 32-bit-torus negacyclic polynomial products with radix 2, '
             'Barrett reduction, baseline profile, and one stage group. '
             f"{sum(p['simulation_passed'] for p in points)}/{len(points)} rows passed "
             'the 12-frame RTL product check. `—` means Yosys did not produce a cell count. '
             'Cells are coarse Yosys operators after memory lowering, not U280 LUTs; '
             'throughput is products per 1,000 cycles without an assumed clock.', '',
             '| Backend | Lanes | PE | Boundary | Error bound | Observed error | Yosys cells | '
             'Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |',
             '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for p in points:
        f = lambda value: f'{value:,}' if isinstance(value, int) else '—'
        rate = p['products_per_1000_cycles']
        formatted_rate = f'{rate:.3f}' if rate is not None else '—'
        lines.append(f"| {p['backend']} | {p['lanes']} | {f(p['pe'])} | {p['boundary']} | "
                     f"{f(p['error_bound'])} | {f(p['observed_error'])} | {f(p['yosys_cells'])} | "
                     f"{f(p['latency_cycles'])} | {f(p['frame_interval_cycles'])} | "
                     f"{formatted_rate} | {p['status']} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path, nargs='+')
    parser.add_argument('--output-md', type=Path, required=True)
    parser.add_argument('--output-csv', type=Path, required=True)
    args = parser.parse_args()
    points = rows(args.evidence)
    args.output_md.write_text(markdown(points))
    with args.output_csv.open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(points[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(points)
    print(f'{len(points)} configurations: {args.output_md}')


if __name__ == '__main__':
    main()
