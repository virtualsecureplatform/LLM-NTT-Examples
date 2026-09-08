#!/usr/bin/env python3
"""Recheck a generated generic candidate with Verilator and the same full oracle suite."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import oracle
from architecture_search.evaluate import generic_testbench,parse_metrics
from architecture_search.model import file_hash,run,source_identity,write_json

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate-dir',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--timeout',type=float,default=3600)
p.add_argument('--externalize-control-roms',action='store_true')
a=p.parse_args();candidate=a.candidate_dir.resolve();out=a.output_dir.resolve()
if not math.isfinite(a.timeout) or a.timeout<=0:p.error('timeout must be finite and positive')
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
recordpath=candidate/'record.json';record=json.loads(recordpath.read_text());manifestpath=candidate.parents[1]/'manifest.json';manifest=json.loads(manifestpath.read_text());w=manifest['campaign']['workload'];oracle.validate(w)
if w.get('kind')!='generic' or record.get('generation',{}).get('returncode')!=0:p.error('generated generic RTL required')
source=Path(record['rtl_path'])
if file_hash(source)!=record['rtl_hash']:p.error('generated RTL changed')
out.mkdir(parents=True);rtl=out/'SearchTop.sv';shutil.copyfile(source,rtl);started=time.monotonic()
roms=[]
if a.externalize_control_roms:
    from externalize_control_roms import externalize
    roms=externalize(rtl)
corpus=oracle.vectors(w)
for name,frames in [('inputs',corpus),('expected',[oracle.transform(v,w) for v in corpus])]:
    (out/(name+'.mem')).write_text(''.join(f'{x:x}\n' for frame in frames for x in frame))
watchdog=int(w.get('watchdog_cycles',max(10000,int(w['n'])*int(w['n']).bit_length()*64)))
(out/'test.sv').write_text(generic_testbench(w,record['configuration']['lanes'],len(corpus),watchdog))
verification={str(path):file_hash(path) for path in [rtl,out/'inputs.mem',out/'expected.mem',out/'test.sv',*[Path(r['path']) for r in roms]]}
write_json(out/'manifest.json',{'schema':'ntt-generic-verilator-check-v1','candidate_record':str(recordpath),'candidate_record_sha256':file_hash(recordpath),'original_manifest':str(manifestpath),'original_manifest_sha256':file_hash(manifestpath),'source':source_identity(ROOT),'workload':w,'configuration':record['configuration'],'verification':verification,'externalized_control_roms':roms,'scope':'Fresh arithmetic oracle vectors and unchanged generic stream/stall/reset testbench; original attempt remains untouched.'})
run(['verilator','--version'],out,out/'version.log',10)
build=run(['verilator','--binary','--timing','--top-module','test','-Wno-fatal','--output-split','10000','--output-split-cfuncs','1000','-j','4',str(rtl),'test.sv'],out,out/'build.log',max(0,a.timeout-(time.monotonic()-started)))
test=run([str(out/'obj_dir/Vtest')],out,out/'test.log',max(0,a.timeout-(time.monotonic()-started))) if build['returncode']==0 else {}
log=(out/'test.log').read_text() if (out/'test.log').exists() else ''
unchanged=all(file_hash(Path(path))==expected for path,expected in verification.items())
result={'correct':test.get('returncode')==0 and 'PASS generic NTT' in log and unchanged,'mode':'functional','metrics':parse_metrics(log),'build':build,'test':test,'verification':verification,'inputs_unchanged':unchanged,'simulator':(out/'version.log').read_text().strip(),'seconds':time.monotonic()-started}
write_json(out/'results.json',result);print(json.dumps({'correct':result['correct'],'metrics':result['metrics'],'results':str(out/'results.json')}))
raise SystemExit(0 if result['correct'] else 1)
