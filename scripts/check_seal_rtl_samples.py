#!/usr/bin/env python3
"""Run captured SEAL inputs/outputs through already-built NGen RTL simulations."""
import argparse,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,run,write_json
from scripts.capture_seal_ntt_trace import natural_order

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture-dir',type=Path,required=True);p.add_argument('--matrix-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    out=a.output_dir.resolve();capture=a.capture_dir.resolve();matrix=a.matrix_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('use a fresh directory')
    trace=json.loads((capture/'results.json').read_text());samples={(s['workload']['q'],s['workload']['direction']):s for s in trace['samples']};rows=[]
    if trace.get('correct') is not True or len(samples)!=8:p.error('complete verified CKKS samples required')
    for case in sorted(matrix.glob('ckks8k-*')):
        w=json.loads((case/'manifest.json').read_text())['campaign']['workload'];sample=samples[(w['q'],w['direction'])]
        if any(w[k]!=sample['workload'][k] for k in ('n','q','psi','root','direction','negacyclic')):raise ValueError('RTL/sample domain mismatch')
        verification=case/'verification';result=json.loads((verification/'results.json').read_text())
        if not result.get('correct'):raise ValueError('original RTL verification failed')
        guard=result['verification'];exe=verification/'obj_dir/Vtest';guard={**guard,str(exe):file_hash(exe)}
        if any(file_hash(Path(k))!=v for k,v in guard.items()):raise ValueError('original RTL verification inputs changed')
        source=capture/'trace'/sample['sample']
        if file_hash(source)!=sample['sha256']:raise ValueError('captured sample changed')
        data=[list(map(int,line.split())) for line in source.read_text().splitlines()];q=int(w['q'])
        inputs=[v[0]%q for v in data];expected=[v[1]%q for v in data]
        if w['direction']=='inverse':inputs=natural_order(inputs)
        else:expected=natural_order(expected)
        frames=int(re.search(r'FRAMES=(\d+)',(verification/'test.sv').read_text()).group(1))
        dest=out/case.name;dest.mkdir(parents=True)
        for name,values in [('inputs',inputs),('expected',expected)]:
            (dest/(name+'.mem')).write_text(''.join(f'{v:x}\n' for _ in range(frames) for v in values))
        guard.update({str(p):file_hash(p) for p in (source,dest/'inputs.mem',dest/'expected.mem')})
        process=run([str(exe)],dest,dest/'test.log',300)
        correct=process['returncode']==0 and 'PASS generic NTT' in (dest/'test.log').read_text() and all(file_hash(Path(k))==v for k,v in guard.items())
        rows.append({'case':case.name,'correct':correct,'process':process,'inputs':guard,'expected_source':'Captured SEAL output, normalized and reordered; no oracle-generated expected vector.'})
        write_json(out/'results.json',{'correct':len(rows)==8 and all(r['correct'] for r in rows),'completed':len(rows),'expected':8,'results':rows,'capture_sha256':file_hash(capture/'results.json'),'scope':'One captured operand/result pair per prime/direction, repeated through the existing gap/backpressure/reset testbench. No full FHE accelerator or timing claim.'})
        print(case.name,'PASS' if correct else 'FAIL',flush=True)
    return 0 if len(rows)==8 and all(r['correct'] for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
