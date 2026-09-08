#!/usr/bin/env python3
"""Verify an extracted preset reference and optionally compare measured NGen runs."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import hardware
from architecture_search.model import digest,file_hash,run,source_identity,write_json
from architecture_search.search import report

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--rtl',type=Path)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--ngen-report',type=Path)
p.add_argument('--hardware',choices=['synthesis','route'])
p.add_argument('--timeout',type=float,default=1200)
a=p.parse_args()
if not math.isfinite(a.timeout) or a.timeout<=0:p.error('timeout must be finite and positive')
campaign=json.loads(a.campaign.read_text());out=a.output_dir.resolve()
if campaign['workload'].get('kind')!='preset':p.error('preset workload required')
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
taskpath=ROOT/'tasks'/(campaign['workload']['task']+'.json');task=json.loads(taskpath.read_text())
if task.get('evaluation',{}).get('mode')!='verilator_test':p.error('independent functional preset test required')
rtl=(a.rtl or ROOT/task['verilog']['default_path']).resolve()
extras=[ROOT/name for name in task['verilog'].get('extra_sources',[])]
for path in [rtl,*extras]:
    if not path.is_file():p.error('missing reference RTL: '+str(path))
identity={'source':source_identity(ROOT),'task_sha256':file_hash(taskpath),'rtl_inputs':{str(path):file_hash(path) for path in [rtl,*extras]}}
target={'part':'xcu280-fsvh2892-2L-e','tool_version':'2023.2','clock_period_ns':4.0,**campaign.get('target',{})};target.setdefault('clock_port',task.get('ports',{}).get('clock','clock'));campaign['target']=target
key=digest({'identity':identity,'campaign':campaign});work=out/'candidates'/key;generated=work/'generated';generated.mkdir(parents=True)
snapshot=generated/task['verilog']['candidate_file'];shutil.copyfile(rtl,snapshot)
record={'schema':'ntt-search-candidate-v1','id':key,'configuration':{'generator':'extracted-rtl','task':task['id']},'status':'running','correct':False,'mode':'functional','rtl_hash':file_hash(snapshot),'rtl_path':str(snapshot),'evidence':{},'provenance':identity}
write_json(work/'record.json',record)
process=run(['bash',str(ROOT/'scripts/evaluate_candidate.sh'),'--task',str(taskpath),'--verilog-file',str(snapshot),'--build-dir',str(work/'evaluation')],ROOT,work/'evaluation.log',a.timeout)
resultpath=work/'evaluation/results.json';raw=json.loads(resultpath.read_text()) if resultpath.exists() else {}
metrics=raw.get('metrics',{});totals=[]
for name in metrics:
    if name.endswith('_input_cycles'):
        prefix=name[:-len('_input_cycles')];parts=[metrics.get(prefix+suffix) for suffix in ('_input_cycles','_max_wait_cycles','_output_cycles')]
        if all(isinstance(value,(int,float)) for value in parts):totals.append(sum(parts))
if totals:metrics['transaction_cycles']=max(totals)
unchanged=all(file_hash(Path(name))==value for name,value in identity['rtl_inputs'].items()) and file_hash(taskpath)==identity['task_sha256'] and file_hash(snapshot)==record['rtl_hash']
correct=process['returncode']==0 and raw.get('correct') is True and raw.get('mode')=='verilator_test' and unchanged
record.update(correct=correct,status='complete' if correct else 'incorrect',evaluation={'correct':correct,'metrics':metrics,'process':process,'inputs_unchanged':unchanged})
record['evidence']['simulation']={'passed':correct,'target':target,'metrics':metrics}
write_json(work/'record.json',record)
if a.hardware and correct:
    evidence=hardware.evaluate(snapshot,task['top_module'],target,metrics,work/a.hardware,a.hardware,10800,extra_sources=extras)
    record['evidence'][a.hardware]=evidence;record['status']='complete' if evidence['passed'] else 'hardware_failed';write_json(work/'record.json',record)
if a.ngen_report:
    baseline=json.loads(a.ngen_report.read_text())
    if baseline['workload']!=campaign['workload']:p.error('NGen workload mismatch')
    for candidate in baseline['candidates']:
        if any(e.get('target')!=target for e in candidate.get('evidence',{}).values()):p.error('NGen target mismatch')
        if candidate.get('rtl_path') and file_hash(Path(candidate['rtl_path']))!=candidate['rtl_hash']:p.error('NGen RTL changed since verification')
        write_json(out/'candidates'/candidate['id']/'record.json',candidate)
write_json(out/'manifest.json',{'schema':'ntt-preset-baseline-comparison-v1','campaign':campaign,'reference':identity,'ngen_report':str(a.ngen_report.resolve()) if a.ngen_report else None,'ngen_report_sha256':file_hash(a.ngen_report) if a.ngen_report else None,'scope':'Same unchanged preset evaluator and task interface. Legacy transaction cycles are not sustained throughput.'})
report(out,campaign)
print(json.dumps({'correct':correct,'metrics':metrics,'report':str(out/'report.json')}))
raise SystemExit(0 if correct and (not a.hardware or record['evidence'][a.hardware]['passed']) else 1)
