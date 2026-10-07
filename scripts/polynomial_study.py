#!/usr/bin/env python3
"""Matched complete-product campaigns; dry runs require no hardware tools."""
import argparse
import csv
import itertools
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import wide_products as wide, wide_backend, product_evaluate, product_simulation
from architecture_search.build_identity import verify
from architecture_search.model import digest, file_hash, write_json, run
from architecture_search.paths import NGEN, SGEN
from scripts.fhe512_preroute import quantize, quantized_rtl, centered_error
from scripts.fhe512_sgen_precision import collected_counts

OBJECTIVES = ('max_abs_error', 'yosys_cells', 'memory_bits', 'register_bits',
              'multipliers', 'latency_cycles', 'initiation_interval_cycles')
BASE = dict(generator='ngen', backend='streamed', lanes=2, pe=1, radix=2,
            stage_groups=1, reduction='barrett', profile='baseline', arithmetic='rns')
AXES = dict(ngen_backends=['streamed', 'stage-parallel'], lanes=[2, 4], pe=[1, 2],
            radix=[2, 4, 8], stage_groups=[1, 2], reductions=['barrett', 'montgomery', 'shoup'])


def workloads(spec):
    if spec.get('schema') != 'polynomial-study-v1':
        raise ValueError('expected polynomial-study-v1')
    if set(spec) - {'schema', 'n', 'workloads', 'fractional_bits', 'omit_low_diagonals',
                    'quant_bits', 'error_limits', 'timeout', 'simulator', 'ngen_axes', 'sgen_axes'}:
        raise ValueError('unknown study field')
    if set(spec.get('ngen_axes', {})) - set(AXES):
        raise ValueError('unknown NTT architecture axis')
    if set(spec.get('sgen_axes', {})) - {'sgen_backends', 'lanes', 'guard_bits'}:
        raise ValueError('unknown FFT architecture axis')
    result = {}
    for p in spec['workloads']:
        name = p['name']
        if not name or any(x not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for x in name) or name in result:
            raise ValueError('workload names must be unique lowercase slugs')
        w = {**wide.workload(spec['n'], modulus=1 << 32),
             'a_range': p['a_range'], 'b_range': p['b_range']}
        wide.validate(w)
        wide.candidates(w, dict(generators=['ngen'], profiles=['baseline'],
                                **{**AXES, **spec.get('ngen_axes', {})}))
        result[name] = w
    if not result:
        raise ValueError('empty workloads')
    for key, legal in [('fractional_bits', [24, 28, 29, 30, 32, 40, 48]),
                       ('omit_low_diagonals', [0, 1, 2]), ('quant_bits', [0, 4, 8])]:
        if not spec[key] or any(type(v) is not int or v not in legal for v in spec[key]):
            raise ValueError('invalid ' + key)
    if 0 not in spec['omit_low_diagonals'] or 0 not in spec['quant_bits']:
        raise ValueError('exact omission and rounding controls are required')
    if not spec['error_limits'] or any(type(v) is not int or v < 0 for v in spec['error_limits']):
        raise ValueError('invalid error limits')
    return result


def point(name, w, c, phase, bits=0, **extra):
    identity = dict(workload=w, configuration=c, quant_bits=bits)
    return dict(name=name + '-' + digest(identity)[:16], workload_name=name,
                workload=w, configuration=c, phase=phase, quant_bits=bits,
                status='pending', **extra)


def enumerate_points(spec):
    points = []
    axes = {**AXES, **spec.get('ngen_axes', {})}
    fft_axes = dict(sgen_backends=['compact'], lanes=[2], guard_bits=[0])
    fft_axes.update(spec.get('sgen_axes', {}))
    for name, w in workloads(spec).items():
        points.append(point(name, w, BASE.copy(), 'arithmetic'))
        for bits in spec['quant_bits']:
            if bits:
                points.append(point(name, w, BASE.copy(), 'rounding', bits))
        for c in wide.candidates(w, dict(generators=['sgen'], **fft_axes,
                 fractional_bits=spec['fractional_bits'],
                 omit_low_diagonals=spec['omit_low_diagonals'])):
            points.append(point(name, w, c, 'arithmetic'))
        # Record the requested Cartesian grid, including combinations rejected by backend rules.
        legal = wide.candidates(w, dict(generators=['ngen'], profiles=['baseline'], **axes))
        for values in itertools.product(*axes.values()):
            a = dict(zip(axes, values))
            c = dict(generator='ngen', backend=a['ngen_backends'], lanes=a['lanes'],
                     radix=a['radix'], stage_groups=a['stage_groups'], reduction=a['reductions'],
                     profile='baseline', arithmetic='rns')
            if c['backend'] == 'streamed':
                c['pe'] = a['pe']
            supported = c in legal and (c['backend'] == 'streamed' or a['pe'] == 1)
            r = point(name, w, c, 'architecture', requested_axes=a)
            if not supported:
                r.update(name=r['name'] + '-unsupported-' + digest(a)[:8], status='unsupported',
                         reason='existing backend legality rules reject this combination')
            elif any(p['name'] == r['name'] for p in points):
                continue
            points.append(r)
        # Precision is chosen from stage-one evidence, not guessed during enumeration.
        for backend, lanes, guard in itertools.product(fft_axes['sgen_backends'], fft_axes['lanes'], fft_axes['guard_bits']):
            selector = dict(backend=backend, lanes=lanes, guard_bits=guard)
            suffix = '' if selector == dict(backend='compact', lanes=2, guard_bits=0) else f'-{backend}-l{lanes}-g{guard}'
            for bits in spec['quant_bits']:
                if bits:
                    points.append(dict(name=name + '-fft' + suffix + '-round-q' + str(bits), workload_name=name,
                                       workload=w, phase='rounding', quant_bits=bits, fft_selector=selector,
                                       status='pending', dependency='lowest-certified-exact-fft'))
    return points


def fft_rounding_parent(rows, dependent):
    exact = [p for p in rows if p['workload_name'] == dependent['workload_name'] and
             p.get('base_qualified') and p.get('configuration', {}).get('generator') == 'sgen'
             and not p['configuration'].get('omit_low_diagonals', 0) and not p['quant_bits']
             and all(p['configuration'].get(k) == v for k, v in dependent['fft_selector'].items())]
    return min(exact, key=lambda p: p['configuration']['fractional_bits']) if exact else None


def corpus(w):
    pairs = wide.vectors(w, random_count=64, seed=1)
    def impulse(key, index):
        values = [0] * w['n']; values[index] = w[key + '_range'][1]
        return values
    if all(lo <= 0 <= hi for lo, hi in (w['a_range'], w['b_range'])):
        pairs.append((impulse('a', w['n'] - 1), impulse('b', 1)))
    return pairs


def expected(w, c, bits, a, b):
    omitted = c.get('omit_low_diagonals', 0)
    values = wide.omitted_product(w, a, b, omitted) if omitted else wide.schoolbook(w, a, b)
    return [quantize(x, bits) for x in values]


def error_metrics(w, c, bits, vectors):
    errors = []
    for a, b in vectors:
        exact = wide.schoolbook(w, a, b)
        errors.extend(centered_error(x, y) for x, y in zip(expected(w, c, bits, a, b), exact))
    bound = wide.omission_error_bound(w, c.get('omit_low_diagonals', 0))
    bound += (1 << (bits - 1)) if bits else 0
    return dict(max_abs_error=bound, observed_max_abs_error=max(map(abs, errors)),
                rms_error=math.sqrt(sum(e * e for e in errors) / len(errors)),
                signed_bias=sum(errors) / len(errors), samples=len(errors),
                tail_counts={str(t): sum(abs(e) > t for e in errors)
                             for t in (0, 8, 115200, 3801600, 4000000)})


def frontier(rows, limit=None):
    eligible = [r for r in rows if r.get('passed') and
                all(type(r.get(k)) in (int, float) and math.isfinite(r[k]) for k in OBJECTIVES)
                and (limit is None or r['max_abs_error'] <= limit)]
    return [r['name'] for r in eligible if not any(
        all(s[k] <= r[k] for k in OBJECTIVES) and any(s[k] < r[k] for k in OBJECTIVES)
        for s in eligible)]


def save(out, spec, rows):
    views = {}
    for name in workloads(spec):
        subset = [r for r in rows if r['workload_name'] == name]
        views[name] = {str(limit): frontier(subset, limit)
                       for limit in [None, 0, *spec['error_limits']]}
    exact = {(r['workload_name'], digest({k: v for k, v in r.get('configuration', {}).items()
              if k != 'omit_low_diagonals'})): r for r in rows
             if r.get('passed') and r['max_abs_error'] == 0}
    for r in rows:
        parent = exact.get((r['workload_name'], digest({k: v for k, v in r.get('configuration', {}).items()
                           if k != 'omit_low_diagonals'})))
        if parent and r.get('passed'):
            r['exact_parent'] = parent['name']
            r['delta_from_exact'] = {k: r[k] - parent[k] for k in OBJECTIVES}
    counts = {s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})}
    write_json(out / 'results.json', dict(schema='polynomial-study-results-v1', points=rows,
                                         coverage=counts, frontiers=views))
    fields = ['name', 'workload_name', 'phase', 'status', 'reason', 'quant_bits', 'prime_count',
              'digit_products', *OBJECTIVES, 'observed_max_abs_error', 'rms_error', 'signed_bias',
              'throughput_products_per_1000_cycles', 'rtl_sha256', 'exact_parent', 'generator', 'backend', 'lanes', 'pe', 'radix',
              'stage_groups', 'reduction', 'fractional_bits', 'omit_low_diagonals']
    with (out / 'all-points.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, extrasaction='ignore'); writer.writeheader()
        writer.writerows({**r, **r.get('configuration', {})} for r in rows)
    lines = ['# Complete polynomial multiplication study', '',
             'Negacyclic products modulo 2^32. Resource counts retain inferred memories; rates use cycles.', '',
             'Coverage: ' + ', '.join(f'{s}: {v}' for s, v in counts.items()), '',
             '| Workload | Point | Status | Error bound | Cells | Memory bits | Latency | Interval |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:
        if r['status'] != 'unsupported':
            lines.append('| ' + ' | '.join(str(r.get(k, '—')) for k in
                ('workload_name', 'name', 'status', 'max_abs_error', 'yosys_cells', 'memory_bits',
                 'latency_cycles', 'initiation_interval_cycles')) + ' |')
    lines += ['', 'Frontiers are separated by workload; exact and error-limited memberships are in results.json.',
              'Bounds are arithmetic screening constraints, not FHE noise qualification.']
    (out / 'summary.md').write_text('\n'.join(lines) + '\n')


def timed_out(result):
    if isinstance(result, dict):
        return bool(result.get('timed_out')) or any(timed_out(v) for v in result.values())
    if isinstance(result, list):
        return any(timed_out(v) for v in result)
    return False


def screen(r, out, timeout, simulator, fft_workers=16, fft_shard_size=4):
    w, c, bits = r['workload'], r['configuration'], r['quant_bits']
    directory = out / r['name']; directory.mkdir(parents=True, exist_ok=True)
    vectors = corpus(w)
    r.update(passed=False, corpus_sha256=digest(vectors))
    if c['generator'] == 'ngen':
        r['prime_count'] = len(wide.basis(w))
    else:
        r['digit_products'] = sum(i + j < 8 and i + j >= c.get('omit_low_diagonals', 0)
            for i in range((wide.input_width(w, 'a') + 3) // 4)
            for j in range((wide.input_width(w, 'b') + 3) // 4))
    if c.get('arithmetic') == 'direct':
        r['digit_products'] = 1
    stage = 'generation'
    try:
        generation, base = wide_backend.generate(w, c, NGEN, SGEN, directory / 'generated', timeout)
        r['generation'] = generation
        if generation['returncode']:
            r.update(status='timeout' if timed_out(generation) else 'generation-failed', reason=stage)
            return
        declared = json.loads(base.with_suffix('.json').read_text())
        r['certificate'] = declared['certificate']
        bound = wide.omission_error_bound(w, c.get('omit_low_diagonals', 0))
        if not wide_backend.qualification_valid(w, declared, base, bound):
            r.update(status='certificate-rejected', reason='numerical or structural certificate rejected')
            return
        r['base_qualified'] = True
        rtl = directory / 'SearchTop.sv'; rtl.write_text(quantized_rtl(base.read_text(), w, bits))
        r.update(rtl_sha256=file_hash(rtl), **error_metrics(w, c, bits, vectors))
        oracle = lambda a, b: expected(w, c, bits, a, b)
        stage = 'simulation'
        checks = {}
        r['simulation'] = checks
        shared = simulator == 'verilator' and c['generator'] == 'sgen' and w['n'] >= 512
        compiled = None
        if shared:
            built, compiled = product_simulation.compile_simulator(w, c, rtl,
                directory / 'compiled', timeout, vectors[-12:], oracle)
            r['simulator_build'] = built
            if compiled is None:
                r.update(status='timeout' if timed_out(built) else 'simulation-failed',
                         reason='simulator compilation'); return
            checks['correctness'] = product_simulation.evaluate_shards(w, c, rtl,
                directory / 'correctness', timeout, vectors, oracle, compiled,
                fft_workers, fft_shard_size)
        else:
            checks['correctness'] = product_evaluate.evaluate(w, c, rtl, directory / 'correctness',
                timeout, simulator, _corpus=vectors, _first_pass=0, _end_pass=1, _output_oracle=oracle)
        if not checks['correctness']['correct']:
            r.update(status='timeout' if timed_out(checks) else 'simulation-failed',
                     reason='correctness'); return
        checks['timing'] = product_evaluate.evaluate(w, c, rtl, directory / 'timing',
            timeout, simulator, _corpus=vectors[-12:], _first_pass=0, _end_pass=1,
            _output_oracle=oracle, **({'_compiled': compiled} if shared else {}))
        if not checks['timing']['correct']:
            r.update(status='timeout' if timed_out(checks) else 'simulation-failed',
                     reason='timing'); return
        if shared:
            checks['protocol'] = product_simulation.evaluate_shards(w, c, rtl,
                directory / 'protocol', timeout, vectors, oracle, compiled,
                fft_workers, fft_shard_size, protocol=True)
        else:
            checks['protocol'] = product_evaluate.evaluate(w, c, rtl, directory / 'protocol',
                timeout, simulator, _corpus=vectors[:64], _first_pass=0, _end_pass=4, _output_oracle=oracle)
        if not checks['protocol']['correct']:
            r.update(status='timeout' if timed_out(checks) else 'simulation-failed',
                     reason='protocol'); return
        # Swapping input positions changes the physical interface widths; generate that contract separately.
        if w['a_range'] != w['b_range']:
            swapped = {**w, 'a_range': w['b_range'], 'b_range': w['a_range']}
            stage = 'swap-generation'
            swap_gen, swap_base = wide_backend.generate(swapped, c, NGEN, SGEN, directory / 'swapped-generated', timeout)
            r['swap_generation'] = swap_gen
            if swap_gen['returncode'] or not wide_backend.qualification_valid(swapped,
                    json.loads(swap_base.with_suffix('.json').read_text()), swap_base, bound):
                r.update(status='timeout' if timed_out(swap_gen) else 'generation-failed', reason=stage)
                return
            swap_rtl = directory / 'Swapped.sv'; swap_rtl.write_text(quantized_rtl(swap_base.read_text(), swapped, bits))
            stage = 'simulation'
            swapped_vectors = [(b, a) for a, b in vectors]
            swapped_oracle = lambda a, b: expected(swapped, c, bits, a, b)
            if shared:
                swap_built, swap_compiled = product_simulation.compile_simulator(swapped, c, swap_rtl,
                    directory / 'swapped-compiled', timeout, swapped_vectors[-12:], swapped_oracle)
                r['swapped_simulator_build'] = swap_built
                if swap_compiled is None:
                    r.update(status='timeout' if timed_out(swap_built) else 'simulation-failed',
                             reason='swapped simulator compilation'); return
                checks['swapped'] = product_simulation.evaluate_shards(swapped, c, swap_rtl,
                    directory / 'swapped', timeout, swapped_vectors, swapped_oracle, swap_compiled,
                    fft_workers, fft_shard_size)
            else:
                checks['swapped'] = product_evaluate.evaluate(swapped, c, swap_rtl, directory / 'swapped',
                    timeout, simulator, _corpus=swapped_vectors, _first_pass=0, _end_pass=1,
                    _output_oracle=swapped_oracle)
        r['simulation'] = checks
        if not all(s['correct'] for s in checks.values()):
            r.update(status='timeout' if timed_out(checks) else 'simulation-failed', reason=stage)
            return
        metrics = checks['timing']['metrics']
        if not all(metrics.get(k, 0) > 0 for k in ('latency_cycles', 'initiation_interval_cycles')):
            r.update(status='simulation-failed', reason='missing positive timing metrics'); return
        r.update({k: metrics[k] for k in ('latency_cycles', 'initiation_interval_cycles')})
        r['throughput_products_per_1000_cycles'] = 1000 / r['initiation_interval_cycles']
        stage = 'synthesis'
        synth = collected_counts(rtl, directory / 'yosys', timeout); r['synthesis'] = synth
        if not synth['passed']:
            r.update(status='timeout' if timed_out(synth) else 'synthesis-failed', reason=stage); return
        counts = synth['counts']; r.update({k: counts[k] for k in ('memory_bits', 'register_bits', 'multipliers')})
        r.update(yosys_cells=counts['cells'], status='screened', passed=True)
        artifacts = [p for p in directory.rglob('*') if p.is_file() and
                     (p.suffix in ('.sv', '.json', '.mem', '.log', '.ys'))]
        r['artifacts'] = {str(p.relative_to(out)): file_hash(p) for p in artifacts}
    except (OSError, ValueError, KeyError, TypeError) as error:
        r.update(status=('generation' if stage == 'swap-generation' else stage) + '-failed', reason=str(error))


def reusable(r, out, requested=None):
    if requested is not None and any(r.get(k) != requested.get(k) for k in
                                     ('configuration', 'workload', 'quant_bits')):
        return False
    evidence = Path(r.get('evidence_root', out))
    return bool(r.get('passed') and r.get('artifacts') and all(
        (evidence / p).is_file() and file_hash(evidence / p) == h for p, h in r['artifacts'].items()))



EVALUATION_SOURCES = {'scripts/polynomial_study.py', 'architecture_search/product_evaluate.py',
                      'architecture_search/product_simulation.py'}


def import_results(results_file, manifest):
    results_file = results_file.resolve()
    source_root = results_file.parent
    source_manifest_file = source_root / 'manifest.json'
    source_manifest = json.loads(source_manifest_file.read_text())
    # Selection may grow from qualification to the complete identical study.
    # Point identity and artifact hashes are checked before any imported reuse.
    for key in ('schema', 'spec', 'tools', 'generators', 'corpora', 'image_sha256'):
        if source_manifest.get(key) != manifest.get(key):
            raise ValueError('reuse manifest differs: ' + key)
    old_sources, new_sources = source_manifest['sources'], manifest['sources']
    for key in old_sources.keys() | new_sources.keys():
        if key not in EVALUATION_SOURCES and old_sources.get(key) != new_sources.get(key):
            raise ValueError('reuse arithmetic/generator source differs: ' + key)
    identity = dict(results_file=str(results_file), results_sha256=file_hash(results_file),
                    manifest_file=str(source_manifest_file), manifest_sha256=file_hash(source_manifest_file))
    imported = {}
    for row in json.loads(results_file.read_text())['points']:
        if reusable(row, source_root):
            imported[row['name']] = {**row, 'evidence_root': str(Path(row.get('evidence_root', source_root))),
                                    'reused_from': identity}
    return imported, identity

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=ROOT / 'studies/torus512.json')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--configuration-names', nargs='+')
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--fft-workers', type=int, default=16)
    parser.add_argument('--fft-shard-size', type=int, default=4)
    parser.add_argument('--reuse-from', type=Path, help='verified results.json from an earlier evaluation campaign')
    args = parser.parse_args(argv)
    try:
        spec = json.loads(args.spec.read_text()); rows = enumerate_points(spec)
        timeout = args.timeout if args.timeout is not None else spec.get('timeout', 1800)
        simulator = spec.get('simulator', 'verilator')
        if not 1 <= args.fft_workers <= 32 or not 1 <= args.fft_shard_size <= 12:
            raise ValueError('FFT workers must be 1..32 and shard size 1..12')
        if args.resume and args.reuse_from:
            raise ValueError('use either --resume or --reuse-from')
        if type(timeout) is not int or timeout <= 0 or simulator not in ('verilator', 'iverilog'):
            raise ValueError('invalid timeout or simulator')
        if args.configuration_names:
            wanted = set(args.configuration_names)
            if wanted - {r['name'] for r in rows}:
                raise ValueError('unknown configuration names')
            # Keep full coverage; selected dependent FFT rounding requires its precision sweep.
            for r in rows:
                if r['name'] not in wanted and r['status'] == 'pending':
                    r['status'] = 'not-selected'
        if args.dry_run:
            print(json.dumps(dict(points=rows, count=len(rows)), indent=2)); return 0
        if args.output_dir is None:
            raise ValueError('--output-dir is required for execution')
        out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
        sources = list((ROOT / 'architecture_search').glob('*.py')) + [Path(__file__),
                  ROOT / 'scripts/fhe512_preroute.py', ROOT / 'scripts/fhe512_sgen_precision.py']
        yosys = Path(os.environ.get('FHE512_YOSYS', ROOT / 'build/tools/bin/yosys')).resolve()
        tools = {name: shutil.which(name) for name in (simulator, 'java', 'vvp') if name != 'vvp' or simulator == 'iverilog'}
        if any(p is None for p in tools.values()) or not yosys.is_file():
            raise ValueError('missing toolchain; use build/tools/bin on PATH and build pinned generators')
        tools['yosys'] = str(yosys)
        version = run([str(yosys), '-V'], out, out / 'yosys.version.log', 30)
        if version['returncode'] or not (out / 'yosys.version.log').read_text().startswith('Yosys 0.50 '):
            raise ValueError('pinned Yosys 0.50 is required')
        identities = {g: verify(root, generator=g) for g, root in [('ngen', NGEN), ('sgen', SGEN)]}
        if not all(i['verified'] for i in identities.values()):
            raise ValueError('generator assemblies missing or stale: ' + json.dumps(identities))
        manifest = dict(schema='polynomial-study-manifest-v1', spec=spec, selected=args.configuration_names,
            sources={str(p.relative_to(ROOT)): file_hash(p) for p in sources},
            tools={k: file_hash(Path(v).resolve()) for k, v in tools.items()}, generators=identities,
            corpora={k: digest(corpus(w)) for k, w in workloads(spec).items()},
            image_sha256=os.environ.get('FHE512_IMAGE_SHA256'),
            evaluation=dict(version=2, fft_workers=args.fft_workers, fft_shard_size=args.fft_shard_size,
                            fft_compiler_optimization='-O3', correctness_fail_fast=True))
        path = out / 'manifest.json'
        if args.resume:
            if not path.is_file():raise ValueError('resume manifest missing')
            old_manifest = json.loads(path.read_text())
            if 'reuse_from' in old_manifest:manifest['reuse_from'] = old_manifest['reuse_from']
            if old_manifest != manifest:
                raise ValueError('resume manifest differs; use a new directory')
        elif path.exists():
            raise ValueError('campaign exists; use --resume')
        imported = {}
        if args.reuse_from:
            imported, reuse_identity = import_results(args.reuse_from, manifest)
            manifest['reuse_from'] = reuse_identity
        write_json(path, manifest)
        previous = {r['name']: r for r in json.loads((out / 'results.json').read_text())['points']} if args.resume and (out / 'results.json').exists() else {}
        previous = {**imported, **previous}
        for index, r in enumerate(rows):
            if r['status'] != 'pending': continue
            if r.get('dependency'):
                parent = fft_rounding_parent(rows, r)
                if parent is None:
                    r.update(status='dependency-rejected', reason='no certified exact FFT baseline'); save(out, spec, rows); continue
                c = parent['configuration']
                rows[index] = r = {**r, 'configuration': c.copy()}
            prior = previous.get(r['name'])
            if prior and reusable(prior, out, r): rows[index] = prior
            else:
                print('Screening ' + r['name'], flush=True); screen(r, out, timeout, simulator, args.fft_workers, args.fft_shard_size)
            save(out, spec, rows)
        save(out, spec, rows)
        return 0 if any(r.get('passed') for r in rows) else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
