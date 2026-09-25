#!/usr/bin/env python3
"""Reproducible N=512 torus-product screening before vendor place and route."""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import product_evaluate, wide_backend, wide_products as wide
from architecture_search.model import digest, file_hash, run, write_json
from architecture_search.paths import NGEN, SGEN


def quantize(value, bits, width=32):
    if not bits:
        return value & ((1 << width) - 1)
    return ((value + (1 << (bits - 1))) >> bits << bits) & ((1 << width) - 1)


def centered_error(actual, exact, width=32):
    value = (actual - exact) & ((1 << width) - 1)
    return value - (1 << width) if value >= (1 << (width - 1)) else value


def error_metrics(w, corpus, bits):
    errors = [centered_error(quantize(x, bits), x)
              for a, b in corpus for x in wide.schoolbook(w, a, b)]
    return dict(max_abs=max(map(abs, errors)), rms=math.sqrt(sum(x*x for x in errors)/len(errors)),
                signed_bias=sum(errors)/len(errors), samples=len(errors),
                analytic_max_abs=(1 << (bits-1)) if bits else 0)


def quantized_rtl(original, w, bits):
    if bits == 0:
        return original
    if not 0 < bits < 32:
        raise ValueError('quantization bits must be 1..31')
    if len(re.findall(r'\bmodule SearchTop\b', original)) != 1:
        raise ValueError('expected exactly one product top')
    body = re.sub(r'\bmodule SearchTop\b', 'module ExactProduct', original)
    aw, bw, ow = wide.input_width(w, 'a'), wide.input_width(w, 'b'), wide.output_width(w)
    if ow != 32:
        raise ValueError('example requires a 32-bit torus output')
    mask = ((1 << ow) - 1) & ~((1 << bits) - 1)
    wrapper = f'''
module SearchTop(input clock,reset,in_valid,output in_ready,
  input [{2*aw-1}:0] a,input [{2*bw-1}:0] b,
  output out_valid,input out_ready,output [{2*ow-1}:0] out_data);
wire [{2*ow-1}:0] exact_data;
ExactProduct core(clock,reset,in_valid,in_ready,a,b,out_valid,out_ready,exact_data);
assign out_data[31:0] = (exact_data[31:0] + 32'd{1 << (bits-1)}) & 32'h{mask:08x};
assign out_data[63:32] = (exact_data[63:32] + 32'd{1 << (bits-1)}) & 32'h{mask:08x};
endmodule
'''
    return body + wrapper


def yosys_counts(rtl, directory, timeout):
    directory.mkdir(parents=True, exist_ok=True)
    binary = Path(os.environ.get('FHE512_YOSYS', ROOT/'build/tools/bin/yosys')).resolve()
    if not binary.is_file():
        raise ValueError('pinned Yosys 0.50 missing; run scripts/build_assurance_yosys.sh')
    script = directory/'synth.ys'
    script.write_text(f'read_verilog -sv "{rtl}"\nhierarchy -check -top SearchTop\n'
                      'proc\nflatten\nmemory\nstat\n')
    process = run([str(binary), '-Q', '-s', str(script)], directory, directory/'yosys.log', timeout)
    result = dict(process=process, rtl_sha256=file_hash(rtl), script_sha256=file_hash(script),
                  yosys_sha256=file_hash(binary), level='coarse-memory-lowered')
    if process['returncode'] == 0:
        log = (directory/'yosys.log').read_text(errors='replace')
        blocks = re.findall(r'=== \\?SearchTop ===\s*(.*?)(?=\n=== |\Z)', log, re.S)
        if blocks:
            section = blocks[-1]
            result['counts'] = {key: int(value) for key, value in
                re.findall(r'Number of (cells|memories|memory bits|wire bits):\s*(\d+)', section)}
            result['cells_by_type'] = {key: int(value) for key, value in
                re.findall(r'^\s+(\$\S+)\s+(\d+)\s*$', section, re.M)}
    result['passed'] = process['returncode'] == 0 and result.get('counts', {}).get('cells', 0) > 0
    write_json(directory/'result.json', result)
    return result


def pareto(rows):
    keys = ('max_abs_error', 'yosys_cells', 'latency_cycles', 'initiation_interval_cycles')
    valid = [r for r in rows if r['passed']]
    return [r['name'] for r in valid if not any(
        all(s[k] <= r[k] for k in keys) and any(s[k] < r[k] for k in keys)
        for s in valid if s is not r)]


def configuration_name(c):
    if c['generator'] == 'sgen':
        return f"sgen-{c['backend']}-l{c['lanes']}-f{c['fractional_bits']}-g{c['guard_bits']}"
    return (f"ngen-{c['backend']}-l{c['lanes']}-pe{c.get('pe', 1)}-r{c['radix']}"
            f"-s{c['stage_groups']}-{c['reduction']}-{c['profile']}"
            + ('-switch' if c.get('transpose', 'indexed') == 'switch' else ''))


def configurations(w, include_sgen, grid='smoke', transposes=('indexed',)):
    if grid == 'smoke':
        ngen = wide.candidates(w, dict(generators=['ngen'], pe=[1, 2], radix=[2],
                                       fractional_bits=[32]))
    elif grid == 'covering':
        pool = wide.candidates(w, dict(generators=['ngen'], ngen_backends=['streamed', 'stage-parallel'],
                                       lanes=[2, 4], pe=[1, 2], radix=[2, 8], stage_groups=[1, 2],
                                       reductions=['barrett', 'montgomery', 'shoup'], profiles=['baseline', 'f300']))
        def selected(c):
            if c['backend'] == 'stage-parallel':
                return c['reduction'] == 'barrett' and c['profile'] == 'baseline'
            standard = c['reduction'] == 'barrett' and c['profile'] == 'baseline' and c['stage_groups'] == 1
            reduction = (c['reduction'] in ('montgomery', 'shoup') and c['profile'] == 'baseline'
                         and c['stage_groups'] == 1 and c['pe'] == 1 and c['radix'] == 2)
            schedule = (c['reduction'] == 'barrett' and c['profile'] == 'baseline'
                        and c['stage_groups'] == 2 and c['pe'] == 1 and c['radix'] == 2)
            profile = (c['reduction'] == 'barrett' and c['profile'] == 'f300'
                       and c['stage_groups'] == 1 and c['pe'] == 1 and c['radix'] == 2)
            return standard or reduction or schedule or profile
        ngen = sorted((c for c in pool if selected(c)),
                      key=lambda c: (c['backend'] != 'streamed', configuration_name(c)))
    else:
        raise ValueError('unknown grid')
    if not transposes or any(t not in ('indexed', 'switch') for t in transposes):
        raise ValueError('transposes must select indexed and/or switch')
    ngen = [{**c, 'transpose': t} if t == 'switch' else c
            for c in ngen for t in dict.fromkeys(transposes)]
    if not include_sgen:
        return ngen
    sgen = wide.candidates(w, dict(generators=['sgen'], fractional_bits=[48],
                                   sgen_backends=['compact']))
    return ngen + sgen


def quantization_points(c, bits, grid):
    if grid == 'smoke' or bits == 0:
        return True
    if c['generator'] == 'sgen':
        return False
    if c['backend'] == 'stage-parallel':
        return c['lanes'] == 4
    return ((c['reduction'] == 'barrett' and c['profile'] == 'baseline' and c['stage_groups'] == 1
             and ((c['lanes'], c['pe'], c['radix']) in ((2, 1, 2), (4, 2, 8))))
            or (c['reduction'] == 'montgomery' and c['lanes'] == 2 and c['pe'] == 1
                and c['radix'] == 2 and c['profile'] == 'baseline' and c['stage_groups'] == 1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--n', type=int, default=512, help='512 for the study; 16 for a quick toolchain check')
    p.add_argument('--bound', type=int, default=2147483647,
                   help='signed operand bound; default is near-full-range 32-bit')
    p.add_argument('--error-limit', type=int, default=16, help='exploratory maximum torus-unit error')
    p.add_argument('--quant-bits', type=int, nargs='+', default=[0, 4], help='output quantization grid')
    p.add_argument('--include-sgen', action='store_true', help='add exact split-FFT baseline; may be costly')
    p.add_argument('--grid', choices=['smoke', 'covering'], default='smoke',
                   help='covering selects 18 NGen architectures and four error variants')
    p.add_argument('--transposes', nargs='+', choices=['indexed', 'switch'], default=['indexed'],
                   help='NGen boundary transpose choices; switch uses a rectangular buffered adapter at N=512')
    p.add_argument('--configuration-names', nargs='+',
                   help='run only these exact architecture names from the selected grid')
    p.add_argument('--resume', action='store_true', help='reuse verified results from the same manifest')
    p.add_argument('--timeout', type=int, default=7200, help='seconds per generation, simulation, or Yosys call')
    a = p.parse_args(argv)
    if a.n < 8 or a.n > 1024 or a.n & (a.n-1) or not 0 < a.bound < (1 << 31):
        p.error('N must be a power of two in 8..1024 and bound must fit signed 32 bits')
    if a.error_limit < 0 or any(k < 0 or k >= 32 for k in a.quant_bits):
        p.error('invalid error limit or quantization bits')
    if a.include_sgen and a.bound > 127:
        p.error('SGen demonstration is limited to bound <=127; larger digit grids need a separate budget')
    out = a.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    yosys_bin = Path(os.environ.get('FHE512_YOSYS', ROOT/'build/tools/bin/yosys')).resolve()
    if not yosys_bin.is_file():
        p.error('pinned Yosys 0.50 missing; run scripts/build_assurance_yosys.sh')
    version = run([str(yosys_bin), '-V'], out, out/'yosys.version.log', 30)
    if version['returncode'] or not (out/'yosys.version.log').read_text().startswith('Yosys 0.50 '):
        p.error('the pre-route example requires pinned Yosys 0.50')
    w = wide.workload(a.n, a.bound, 'negacyclic', 1 << 32)
    vectors = wide.vectors(w, random_count=4, seed=512)
    corpus = vectors[:8] + vectors[-4:]
    configs = configurations(w, a.include_sgen, a.grid, a.transposes)
    if a.configuration_names:
        wanted = set(a.configuration_names)
        available = {configuration_name(c) for c in configs}
        if len(wanted) != len(a.configuration_names) or wanted - available:
            p.error('configuration names must be unique members of the selected grid: '
                    + ', '.join(sorted(wanted - available)))
        configs = [c for c in configs if configuration_name(c) in wanted]
    manifest = dict(schema='fhe512-preroute-example-v2', workload=w, configurations=configs, grid=a.grid,
                    quant_bits=sorted(set(a.quant_bits)), error_limit=a.error_limit,
                    corpus_sha256=digest(corpus), image_sha256=os.environ.get('FHE512_IMAGE_SHA256'),
                    runner_sha256=file_hash(Path(__file__)),
                    tools={'yosys':{**version, 'sha256':file_hash(yosys_bin)},
                           **{name: run([name, option], out, out/(name+'.version.log'), 30)
                              for name, option in [('iverilog','-V'), ('java','-version')]}})
    old_manifest = out/'manifest.json'
    if a.resume and old_manifest.is_file():
        old = json.loads(old_manifest.read_text())
        stable = ('schema', 'workload', 'configurations', 'grid', 'quant_bits', 'error_limit',
                  'corpus_sha256', 'image_sha256', 'runner_sha256')
        if any(old.get(key) != manifest.get(key) for key in stable) or old['tools']['yosys']['sha256'] != manifest['tools']['yosys']['sha256']:
            p.error('resume manifest differs; use a new output directory')
    elif a.resume:
        p.error('resume requires an existing manifest')
    write_json(old_manifest, manifest)
    rows = []
    for c in configs:
        label = configuration_name(c)
        directory = out/label; directory.mkdir(exist_ok=True)
        rtl = directory/'generated'/'SearchTop.sv'
        if a.resume and rtl.is_file() and rtl.with_suffix('.json').is_file() and wide_backend.qualification_valid(
                w, json.loads(rtl.with_suffix('.json').read_text()), rtl):
            generation = dict(returncode=0, numerically_qualified=True, resumed=True)
            print(f'Reusing verified generation {label}', flush=True)
        else:
            print(f'Generating {label}', flush=True)
            generation, rtl = wide_backend.generate(w, c, NGEN, SGEN, directory/'generated', a.timeout)
        if generation['returncode'] or not generation.get('numerically_qualified'):
            rows.append(dict(name=label, passed=False, reason='generation or exact certificate failed', generation=generation))
            print(f'{label}: generation or exact certificate failed', flush=True)
            continue
        if not wide_backend.qualification_valid(w, json.loads(rtl.with_suffix('.json').read_text()), rtl):
            rows.append(dict(name=label, passed=False, reason='base product qualification failed'))
            print(f'{label}: base qualification failed', flush=True)
            continue
        base = rtl.read_text()
        for bits in sorted(set(a.quant_bits)):
            if not quantization_points(c, bits, a.grid):
                continue
            name = label + '-q' + str(bits); candidate = directory/('q'+str(bits))
            candidate.mkdir(exist_ok=True); path = candidate/'SearchTop.sv'
            path.write_text(quantized_rtl(base, w, bits))
            point_file = candidate/'point.json'
            if a.resume and point_file.is_file():
                prior = json.loads(point_file.read_text())
                sim_file = candidate/'simulation'/'results.json'
                yosys_file = candidate/'yosys'/'result.json'
                if (prior.get('rtl_sha256') == file_hash(path) and prior.get('passed') is True
                    and sim_file.is_file() and json.loads(sim_file.read_text()).get('correct') is True
                    and yosys_file.is_file() and json.loads(yosys_file.read_text()).get('passed') is True):
                    rows.append(prior)
                    print(f'Reusing verified point {name}', flush=True)
                    write_json(out/'results.json', dict(manifest=manifest, points=rows, frontier=pareto(rows)))
                    continue
            em = error_metrics(w, corpus, bits)
            mapped = lambda values, k=bits: [quantize(x, k) for x in values]
            print(f'Simulating {name}', flush=True)
            sim = product_evaluate.evaluate(w, c, path, candidate/'simulation', a.timeout,
                                            'iverilog', _corpus=corpus, _first_pass=0,
                                            _end_pass=1, _output_map=mapped)
            if sim['correct']:
                print(f'Yosys screening {name}', flush=True)
            synth = yosys_counts(path, candidate/'yosys', a.timeout) if sim['correct'] else {'passed':False}
            metrics = sim.get('metrics', {}); counts = synth.get('counts', {})
            row = dict(name=name, configuration=c, quant_bits=bits,
                       max_abs_error=em['analytic_max_abs'], observed_max_abs_error=em['max_abs'], error=em,
                       yosys_cells=counts.get('cells'), yosys_counts=counts,
                       latency_cycles=metrics.get('latency_cycles'),
                       initiation_interval_cycles=metrics.get('initiation_interval_cycles'),
                       throughput_products_per_1000_cycles=(1000/metrics['initiation_interval_cycles']
                           if metrics.get('initiation_interval_cycles', 0) > 0 else None),
                       passed=sim['correct'] and synth['passed'] and em['analytic_max_abs'] <= a.error_limit,
                       qualification='analytically bounded output quantization; sampled product verification',
                       simulation_passed=sim['correct'], yosys_passed=synth['passed'],
                       rtl_sha256=file_hash(path))
            rows.append(row); write_json(candidate/'point.json', row)
            write_json(out/'results.json', dict(manifest=manifest, points=rows, frontier=pareto(rows)))
            print(f'{name}: simulation={sim["correct"]} yosys={synth["passed"]} max_error={em["max_abs"]}', flush=True)
    result = dict(manifest=manifest, points=rows, frontier=pareto(rows),
                  limitations='Yosys generic cells and cycle counts only; no U280 resources, clock, or FHE noise qualification')
    write_json(out/'results.json', result)
    return 0 if result['frontier'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
