#!/usr/bin/env python3
"""Copy completed Yosys reruns into an existing FHE512 campaign result."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fhe512_preroute import pareto, yosys_counts
from architecture_search.model import file_hash, write_json


def refresh(directory):
    result_file = directory / 'results.json'
    result = json.loads(result_file.read_text())
    updated = 0
    for point in result['points']:
        candidate = directory / point['name'].rsplit('-q', 1)[0] / ('q' + str(point['quant_bits']))
        rtl = candidate / 'SearchTop.sv'
        yosys_file = candidate / 'yosys' / 'result.json'
        if not yosys_file.is_file():
            continue
        synth = json.loads(yosys_file.read_text())
        if point['rtl_sha256'] != synth['rtl_sha256'] or file_hash(rtl) != synth['rtl_sha256']:
            raise ValueError(f'RTL hash mismatch for {candidate}')
        counts = synth.get('counts', {})
        changes = dict(yosys_cells=counts.get('cells'), yosys_counts=counts,
                       yosys_passed=synth['passed'],
                       passed=(point['simulation_passed'] and synth['passed']
                               and point['max_abs_error'] <= result['manifest']['error_limit']))
        if any(point.get(key) != value for key, value in changes.items()):
            point.update(changes)
            write_json(candidate / 'point.json', point)
            updated += 1
    result['frontier'] = pareto(result['points'])
    write_json(result_file, result)
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--timeout', type=int,
                        help='rerun Yosys for selected existing points with this per-point limit')
    parser.add_argument('--configuration-names', nargs='+',
                        help='exact architecture names to rerun; requires --timeout')
    args = parser.parse_args()
    if bool(args.timeout) != bool(args.configuration_names) or (args.timeout is not None and args.timeout <= 0):
        parser.error('--timeout must be positive and paired with --configuration-names')
    directory = args.output_dir.resolve()
    if args.configuration_names:
        result = json.loads((directory / 'results.json').read_text())
        points = {point['name']: point for point in result['points']}
        wanted = set(args.configuration_names)
        if len(wanted) != len(args.configuration_names) or any(name + '-q0' not in points for name in wanted):
            parser.error('configuration names must be unique existing exact points')
        for name in args.configuration_names:
            point = points[name + '-q0']
            if not point['simulation_passed']:
                parser.error(f'simulation did not pass for {name}')
            candidate = directory / name / 'q0'
            rtl = candidate / 'SearchTop.sv'
            if file_hash(rtl) != point['rtl_sha256']:
                raise ValueError(f'RTL hash mismatch for {rtl}')
            print(f'Yosys screening {name} ({args.timeout}s)', flush=True)
            yosys_counts(rtl, candidate / 'yosys', args.timeout)
    updated = refresh(directory)
    print(f'{updated} points updated in {args.output_dir / "results.json"}')


if __name__ == '__main__':
    main()
