#!/usr/bin/env python3
"""Generate and verify a dual-direction NGen preloaded-compute boundary."""
import argparse,copy,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import adapters,preloaded_ntt,oracle,hardware,autontt_research
from architecture_search.model import write_json,run,artifact_manifest
ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workload',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--backend',choices=['streamed','stage-parallel'],default='streamed')
    p.add_argument('--lanes',type=int,default=4);p.add_argument('--pe',type=int,default=2)
    p.add_argument('--hardware',choices=['synthesis','route']);p.add_argument('--reduction',choices=['barrett','montgomery','shoup','auto'],default='barrett');a=p.parse_args(argv)
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'PreloadedNTT.sv').exists():raise ValueError('use a fresh output directory')
    w=json.loads(a.workload.read_text());w.setdefault('negacyclic',False);oracle.validate(w)
    space=dict(backends=[a.backend],pe=[a.pe],radix=[2],stage_groups=[1],reductions=[a.reduction],profiles=['baseline'])
    generic=dict(w,kind='generic',lanes=a.lanes)
    configurations=adapters.candidates(generic,ROOT/'third_party/NGen',space)
    if len(configurations)!=1:raise ValueError('expected one bounded architecture')
    c=configurations[0];cores=[];generation=[];metadata=[]
    for direction in ('forward','inverse'):
        process,path=adapters.generate(dict(generic,direction=direction),c,ROOT/'third_party/NGen',out/direction,600)
        if process['returncode']:raise ValueError('NGen failed')
        generation.append(process);metadata.append(json.loads(path.with_suffix('.json').read_text()));cores.append(preloaded_ntt.namespace(path.read_text(),direction.title()))
    rtl=out/'PreloadedNTT.sv';rtl.write_text('\n'.join(cores+[preloaded_ntt.wrapper(w,a.lanes)]))
    rng=random.Random(71);n,q=w['n'],int(w['q'])
    vectors=[[0]*n,[q-1]*n,[1]+[0]*(n-1)]+[[rng.randrange(q) for _ in range(n)] for _ in range(8)]
    for name,text in preloaded_ntt.fixtures(w,a.lanes,vectors).items():(out/name).write_text(text)
    (out/'test.sv').write_text(preloaded_ntt.testbench(w,a.lanes,vectors))
    inputs=artifact_manifest([rtl,out/'test.sv',out/'input.mem',out/'expected.mem',a.workload.resolve()])
    build=run(['verilator','--binary','--timing','-CFLAGS','-std=c++20','--top-module','test','-Wno-fatal','-j','4',str(rtl),'test.sv'],out,out/'build.log',3600)
    test=run([str(out/'obj_dir/Vtest')],out,out/'test.log',3600) if build['returncode']==0 else {}
    passed=build['returncode']==0 and test.get('returncode')==0 and 'PASS preloaded transform' in (out/'test.log').read_text()
    result=dict(schema='ngen-preloaded-v1',generator='ngen',architecture=c,workload=w,boundary=autontt_research.BOUNDARY,
        correct=passed,generation=generation,cores=metadata,functional=dict(build=build,test=test),inputs=inputs,
        initialization_measured_separately=True,initialization_cycles_per_frame=n//a.lanes,
        note='Two distinct fixed-direction cores plus shared counted operand/result memories. Functional counters exclude preload/readback.')
    if passed and inputs!=artifact_manifest(inputs['files'],inputs['directories']):raise ValueError('functional inputs changed')
    functional=dict(passed=passed,metrics=dict(checked_coefficients=2*n*len(vectors)))
    functional['integrity']=dict(version=1,inputs_unchanged=inputs==artifact_manifest(inputs['files'],inputs['directories']),
        inputs=inputs,outputs=artifact_manifest([out/'build.log',out/'test.log']),measurement=copy.deepcopy(functional))
    result['evidence']={'functional':functional}
    if passed and a.hardware:
        rows=[line.split() for line in (out/'test.log').read_text().splitlines() if line.startswith('PRELOADED ')]
        metrics=dict(latency_cycles=max(int(row[3]) for row in rows))
        target=dict(part='xcu280-fsvh2892-2L-e',tool_version='2023.2',clock_period_ns=4,input_hold_buffer_stages=1)
        result['evidence'][a.hardware]=hardware.evaluate(rtl,'PreloadedNTT',target,metrics,out/a.hardware,a.hardware,10800)
    result['artifacts']=artifact_manifest([rtl,out/'test.sv',out/'build.log',out/'test.log'])
    result['passed']=passed and (not a.hardware or result['evidence'][a.hardware]['passed'])
    write_json(out/'result.json',result);return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
