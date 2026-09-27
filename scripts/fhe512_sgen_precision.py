#!/usr/bin/env python3
"""Screen exact and bounded-error SGen N=512 torus products before routing."""
import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import product_evaluate, wide_backend, wide_products as wide
from architecture_search.model import digest, file_hash, run, write_json
from architecture_search.paths import NGEN, SGEN
from scripts.fhe512_preroute import centered_error, configuration_name


def corpus(w):
    n=w['n'];lo,hi=w['a_range'];random_pairs=wide.vectors(w,random_count=1,seed=512)
    return [([hi]*n,[hi]*n),
            ([lo if i&1 else hi for i in range(n)],
             [hi if i&1 else lo for i in range(n)]),
            random_pairs[-1]]


def measured_error(w,vectors,omitted):
    errors=[]
    for a,b in vectors:
        exact=wide.schoolbook(w,a,b)
        actual=wide.omitted_product(w,a,b,omitted) if omitted else exact
        errors.extend(centered_error(x,y) for x,y in zip(actual,exact))
    thresholds=(0,16,1024,65536,131072,4000000)
    return dict(observed_max_abs_error=max(map(abs,errors)),
                rms_error=math.sqrt(sum(e*e for e in errors)/len(errors)),
                signed_bias=sum(errors)/len(errors),samples=len(errors),
                tail_counts={str(t):sum(abs(e)>t for e in errors) for t in thresholds})


def collected_counts(rtl,directory,timeout):
    """Retain inferred memories so large FFT products remain screenable."""
    directory.mkdir(parents=True,exist_ok=True)
    binary=Path(os.environ.get('FHE512_YOSYS',ROOT/'build/tools/bin/yosys')).resolve()
    script=directory/'synth.ys';netlist=directory/'collected.json'
    script.write_text(f'read_verilog -sv "{rtl}"\nhierarchy -check -top SearchTop\n'
                      f'proc\nflatten\nmemory_collect\nstat\nwrite_json "{netlist}"\n')
    process=run([str(binary),'-Q','-s',str(script)],directory,directory/'yosys.log',timeout)
    result=dict(process=process,level='coarse-memory-collected',rtl_sha256=file_hash(rtl),
                script_sha256=file_hash(script),yosys_sha256=file_hash(binary))
    if process['returncode']==0 and netlist.is_file():
        cells=json.loads(netlist.read_text())['modules']['SearchTop']['cells']
        type_counts={kind:sum(cell['type']==kind for cell in cells.values())
                     for kind in {cell['type'] for cell in cells.values()}}
        memories=[cell for cell in cells.values() if cell['type']=='$mem_v2']
        sequential=[cell for cell in cells.values() if cell['type'] in ('$dff','$adff','$sdff','$dffe','$adffe')]
        result['counts']=dict(cells=len(cells),operators=len(cells)-len(memories)-len(sequential),
                              register_bits=sum(int(cell['parameters']['WIDTH'],2) for cell in sequential),
                              memory_blocks=len(memories),
                              memory_bits=sum(int(cell['parameters']['SIZE'],2)*int(cell['parameters']['WIDTH'],2)
                                              for cell in memories),multipliers=type_counts.get('$mul',0))
        result['cells_by_type']=type_counts
        result['netlist_sha256']=file_hash(netlist)
    result['passed']=process['returncode']==0 and result.get('counts',{}).get('cells',0)>0
    write_json(directory/'result.json',result)
    return result


def frontier(rows):
    keys=('max_abs_error','yosys_cells','memory_bits','register_bits','multipliers',
          'latency_cycles','initiation_interval_cycles')
    valid=[row for row in rows if row.get('passed')]
    return [row['name'] for row in valid if not any(
        all(other[key]<=row[key] for key in keys) and any(other[key]<row[key] for key in keys)
        for other in valid if other is not row)]


def markdown(rows,w,error_limit):
    lines=[f"# N={w['n']} SGen torus-product precision sweep",'',
           f"Input coefficients are in {w['a_range']}; outputs are modulo 2^32. "
           f"The exploratory coefficient-error limit is {error_limit:,} torus units. "
           'Each complete product uses two input and output lanes and the compact SGen FFT. '
           'A lower-digit omission removes exact radix-16 digit products from the serial schedule. '
           'The reported worst-case bound covers that omission; it is not an FHE noise budget.','',
           'Coarse Yosys cells retain memory macros; memory bits and register bits are separate resource measures. '
           'These are not U280 LUTs or BRAMs. '
           'Throughput is products per 1,000 cycles without an assumed clock.','',
           '| Fractional bits | Omitted low diagonals | Digit products | Error bound | Observed max error | '
           'RMS error | Yosys cells | Memory bits | Register bits | Multipliers | Latency cycles | '
           'Frame interval cycles | Products / 1,000 cycles | Status |',
           '| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    fmt=lambda v:f'{v:,}' if isinstance(v,int) else '—'
    for row in rows:
        rate=row.get('throughput_products_per_1000_cycles')
        rms=f"{row['rms_error']:.2f}" if row.get('rms_error') is not None else '—'
        throughput=f'{rate:.3f}' if rate is not None else '—'
        lines.append(f"| {row['fractional_bits']} | {row['omit_low_diagonals']} | {row['digit_products']} | "
                     f"{fmt(row.get('max_abs_error'))} | {fmt(row.get('observed_max_abs_error'))} | "
                     f"{rms} | {fmt(row.get('yosys_cells'))} | {fmt(row.get('memory_bits'))} | "
                     f"{fmt(row.get('register_bits'))} | {fmt(row.get('multipliers'))} | "
                     f"{fmt(row.get('latency_cycles'))} | "
                     f"{fmt(row.get('initiation_interval_cycles'))} | {throughput} | {row['status']} |")
    return '\n'.join(lines)+'\n'


def save(out,manifest,rows):
    nondominated=frontier(rows)
    result=dict(schema='fhe512-sgen-precision-v1',manifest=manifest,points=rows,frontier=nondominated,
                limitation='Exploratory torus-error bounds and coarse Yosys counts; no FHE noise qualification or U280 timing')
    write_json(out/'results.json',result)
    (out/'summary.md').write_text(markdown(rows,manifest['workload'],manifest['error_limit']))
    fields=('name','fractional_bits','omit_low_diagonals','digit_products','max_abs_error',
            'observed_max_abs_error','rms_error','signed_bias','yosys_cells','memory_bits',
            'register_bits','multipliers','latency_cycles',
            'initiation_interval_cycles','throughput_products_per_1000_cycles','simulation_passed',
            'yosys_passed','status','rtl_sha256')
    with (out/'all-points.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--n',type=int,default=512)
    p.add_argument('--bound',type=int,default=2147483647)
    p.add_argument('--fractional-bits',type=int,nargs='+',default=[30,32])
    p.add_argument('--omit-low-diagonals',type=int,nargs='+',default=[0,1,2])
    p.add_argument('--error-limit',type=int,default=4000000)
    p.add_argument('--timeout',type=int,default=1800)
    p.add_argument('--simulator',choices=('verilator','iverilog'),default='verilator')
    p.add_argument('--configuration-names',nargs='+')
    p.add_argument('--resume',action='store_true')
    args=p.parse_args(argv)
    if args.n<8 or args.n>1024 or args.n&(args.n-1) or not 0<args.bound<1<<31:
        p.error('N must be a power of two in 8..1024 and bound must fit signed 32 bits')
    if args.error_limit<0:p.error('error limit must be nonnegative')
    w=wide.workload(args.n,args.bound,'negacyclic',1<<32)
    options=dict(generators=['sgen'],sgen_backends=['compact'],lanes=[2],
                 fractional_bits=sorted(set(args.fractional_bits)),guard_bits=[0],
                 omit_low_diagonals=sorted(set(args.omit_low_diagonals)))
    try:configs=wide.candidates(w,options)
    except ValueError as error:p.error(str(error))
    if args.configuration_names:
        names=set(args.configuration_names);available={configuration_name(c) for c in configs}
        if len(names)!=len(args.configuration_names) or names-available:p.error('unknown or duplicate configuration names')
        configs=[c for c in configs if configuration_name(c) in names]
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    vectors=corpus(w)
    yosys=Path(os.environ.get('FHE512_YOSYS',ROOT/'build/tools/bin/yosys')).resolve()
    version=run([str(yosys),'-V'],out,out/'yosys.version.log',30)
    if version['returncode'] or not (out/'yosys.version.log').read_text().startswith('Yosys 0.50 '):
        p.error('pinned Yosys 0.50 is required')
    simulator=run([args.simulator,'--version' if args.simulator=='verilator' else '-V'],
                  out,out/'simulator.version.log',30)
    if simulator['returncode']:p.error('selected simulator is unavailable')
    sources=[Path(__file__),ROOT/'architecture_search/wide_products.py',ROOT/'architecture_search/wide_rtl.py',
             ROOT/'architecture_search/wide_backend.py',ROOT/'architecture_search/product_evaluate.py']
    manifest=dict(schema='fhe512-sgen-precision-manifest-v1',workload=w,configurations=configs,
                  error_limit=args.error_limit,corpus_sha256=digest(vectors),simulator=args.simulator,
                  image_sha256=os.environ.get('FHE512_IMAGE_SHA256'),
                  source_sha256={str(s.relative_to(ROOT)):file_hash(s) for s in sources},
                  yosys_sha256=file_hash(yosys),
                  simulator_version=(out/'simulator.version.log').read_text().strip())
    manifest_file=out/'manifest.json'
    if args.resume:
        if not manifest_file.is_file() or json.loads(manifest_file.read_text())!=manifest:
            p.error('resume manifest differs; use a new output directory')
    elif manifest_file.is_file():p.error('output directory already contains a campaign; use --resume')
    write_json(manifest_file,manifest)
    old={r['name']:r for r in json.loads((out/'results.json').read_text())['points']} if args.resume and (out/'results.json').is_file() else {}
    rows=[]
    for c in configs:
        name=configuration_name(c);omit=c.get('omit_low_diagonals',0)
        directory=out/name;generated=directory/'generated';rtl=generated/'SearchTop.sv'
        bound=wide.omission_error_bound(w,omit)
        digit_products=sum(i+j>=omit and i+j<8 for i in range(8) for j in range(8)) if wide.input_width(w,'a')==32 else sum(
            i+j>=omit and i+j<8 for i in range((wide.input_width(w,'a')+3)//4)
            for j in range((wide.input_width(w,'b')+3)//4))
        previous=old.get(name)
        if previous and previous.get('passed') and rtl.is_file() and previous.get('rtl_sha256')==file_hash(rtl):
            rows.append(previous);save(out,manifest,rows);print(f'Reusing {name}',flush=True);continue
        print(f'Generating {name}',flush=True)
        generated_result,rtl=wide_backend.generate(w,c,NGEN,SGEN,generated,args.timeout)
        row=dict(name=name,configuration=c,fractional_bits=c['fractional_bits'],omit_low_diagonals=omit,
                 digit_products=digit_products,max_abs_error=bound)
        if generated_result['returncode']:
            row.update(passed=False,status='generation failed',simulation_passed=False,yosys_passed=False)
            rows.append(row);save(out,manifest,rows);continue
        descriptor=json.loads(rtl.with_suffix('.json').read_text())
        numeric=descriptor['certificate']
        row.update(rtl_sha256=file_hash(rtl),leaf_certificate=numeric['leaf_certificate'],
                   generation_assurance_passed=generated_result['assurance_passed'])
        if not wide_backend.qualification_valid(w,descriptor,rtl,args.error_limit):
            row.update(passed=False,status='numerical certificate or error limit rejected',
                       simulation_passed=False,yosys_passed=False)
            rows.append(row);save(out,manifest,rows);print(f'{name}: {row["status"]}',flush=True);continue
        error=measured_error(w,vectors,omit);row.update(error)
        oracle=(lambda a,b,k=omit:wide.omitted_product(w,a,b,k)) if omit else None
        print(f'Simulating {name}',flush=True)
        sim=product_evaluate.evaluate(w,c,rtl,directory/'simulation',args.timeout,args.simulator,
                                      _corpus=vectors,_first_pass=0,_end_pass=1,_output_oracle=oracle)
        row['simulation_passed']=sim['correct']
        if sim['correct']:
            print(f'Yosys screening {name}',flush=True)
            synth=collected_counts(rtl,directory/'yosys',args.timeout)
        else:synth={'passed':False}
        metrics=sim.get('metrics',{});counts=synth.get('counts',{})
        row.update(yosys_cells=counts.get('cells'),memory_bits=counts.get('memory_bits'),
                   register_bits=counts.get('register_bits'),multipliers=counts.get('multipliers'),
                   latency_cycles=metrics.get('latency_cycles'),
                   initiation_interval_cycles=metrics.get('initiation_interval_cycles'),
                   throughput_products_per_1000_cycles=1000/metrics['initiation_interval_cycles']
                   if metrics.get('initiation_interval_cycles',0)>0 else None,
                   yosys_passed=synth['passed'],passed=sim['correct'] and synth['passed'],
                   status='screened' if sim['correct'] and synth['passed'] else
                   'simulation failed' if not sim['correct'] else 'Yosys failed')
        rows.append(row);save(out,manifest,rows)
        print(f'{name}: {row["status"]}, observed error {error["observed_max_abs_error"]}',flush=True)
    return 0 if any(r.get('passed') for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
