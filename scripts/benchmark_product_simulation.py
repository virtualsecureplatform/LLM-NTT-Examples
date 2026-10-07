#!/usr/bin/env python3
"""Compare -Os and -O3 on identical complete-product RTL and random frames."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import product_evaluate, product_simulation, wide_backend
from architecture_search.model import file_hash, digest, write_json
from scripts.polynomial_study import corpus, expected
from scripts.fhe512_preroute import quantized_rtl
from architecture_search.wide_products import omission_error_bound


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir', type=Path, required=True)
    parser.add_argument('--configuration-name', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=1)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args(argv)
    if not 1 <= args.frames <= 12 or args.timeout <= 0:
        parser.error('frames must be 1..12 and timeout positive')
    source = args.campaign_dir.resolve()
    row = next(r for r in json.loads((source / 'results.json').read_text())['points']
               if r['name'] == args.configuration_name)
    w, c, bits = row['workload'], row['configuration'], row['quant_bits']
    rtl = source / row['name'] / 'SearchTop.sv'
    base = source / row['name'] / 'generated/SearchTop.sv'
    if file_hash(rtl) != row['rtl_sha256'] or not wide_backend.qualification_valid(w,
            json.loads(base.with_suffix('.json').read_text()), base,
            omission_error_bound(w, c.get('omit_low_diagonals', 0))):
        parser.error('source RTL/certificate identity failed')
    if rtl.read_text() != quantized_rtl(base.read_text(), w, bits):
        parser.error('source product wrapper differs')
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    vectors = corpus(w)
    # The last corpus entry is the wraparound impulse; use seeded random frames.
    frames = vectors[-args.frames - 1:-1]
    oracle = lambda a, b: expected(w, c, bits, a, b)
    results = {}
    for flag in ('-Os', '-O3'):
        print('Benchmarking ' + flag, flush=True)
        built, compiled = product_simulation.compile_simulator(w, c, rtl,
            out / flag[1:] / 'compiled', args.timeout, vectors[-12:], oracle, flag)
        if compiled is None:
            results[flag] = dict(build=built, correct=False)
        else:
            checked = product_evaluate.evaluate(w, c, rtl, out / flag[1:] / 'simulation',
                args.timeout, 'verilator', _corpus=frames, _first_pass=0, _end_pass=1,
                _output_oracle=oracle, _compiled=compiled)
            results[flag] = dict(build=built, simulation=checked, correct=checked['correct'])
        write_json(out / 'benchmark.json', dict(configuration=row['name'], frames=args.frames,
            corpus_sha256=digest(frames), rtl_sha256=file_hash(rtl), results=results,
            source_sha256={str(p.relative_to(ROOT)): file_hash(p) for p in
                [Path(__file__), ROOT / 'architecture_search/product_simulation.py',
                 ROOT / 'architecture_search/product_evaluate.py']}))
    report = json.loads((out / 'benchmark.json').read_text())
    if all(r['correct'] for r in results.values()):
        report['speedup'] = results['-Os']['simulation']['test']['seconds'] / results['-O3']['simulation']['test']['seconds']
        write_json(out / 'benchmark.json', report)
        print('Simulator speedup: %.3fx' % report['speedup'], flush=True)
        return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
