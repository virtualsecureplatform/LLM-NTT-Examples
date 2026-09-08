#!/usr/bin/env python3
"""Run singleton generic campaigns with snapshotted NGen and full Verilator oracles."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.adapters import candidates,generate
from architecture_search.build_identity import verify
from architecture_search.model import file_hash,run,source_identity,write_json

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign-dir',type=Path,required=True)
p.add_argument('--ngen-root',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--timeout',type=float,default=7200,help='seconds per generation and per complete oracle check')
a=p.parse_args();out=a.output_dir.resolve();ngen=a.ngen_root.resolve()
if not math.isfinite(a.timeout) or a.timeout<=0:p.error('timeout must be finite and positive')
build=verify(ngen)
if not build['verified']:p.error('NGen build verification failed; run sbt assembly: '+str(build))
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
campaigns=[]
for path in sorted(a.campaign_dir.glob('*.json')):
    c=json.loads(path.read_text())
    if c['workload'].get('kind')!='generic':p.error('generic campaigns required')
    configs=candidates(c['workload'],ngen,c['space'])
    if len(configs)!=1:p.error('each campaign must specify exactly one legal configuration')
    campaigns.append((path,c,configs[0]))
if not campaigns:p.error('no campaigns')
out.mkdir(parents=True,exist_ok=True);binary=out/'ngen.bat';shutil.copyfile(ngen/'ngen.bat',binary)
guarded=[*sorted((ROOT/'architecture_search').glob('*.py')),ROOT/'scripts/check_generic_verilator.py',ROOT/'scripts/externalize_control_roms.py',Path(__file__).resolve()]
identities={str(path):file_hash(path) for path in guarded}
manifest={'schema':'ntt-fhe-verilator-matrix-v1','ngen_build':build,'ngen_source':source_identity(ngen),'binary_sha256':file_hash(binary),'runner_files':identities,'campaigns':{str(path.resolve()):file_hash(path) for path,_,_ in campaigns},'scope':'Independent registered-stream oracle checks; no hardware performance or fit claim.'}
write_json(out/'manifest.json',manifest);results=[]
for path,c,config in campaigns:
    if file_hash(binary)!=manifest['binary_sha256'] or any(file_hash(Path(name))!=value for name,value in identities.items()):raise RuntimeError('executable input changed during matrix')
    case=out/path.stem;candidate=case/'candidates'/'candidate'
    write_json(case/'manifest.json',{'campaign':c,'matrix_manifest_sha256':file_hash(out/'manifest.json')})
    generation,rtl=generate(c['workload'],config,ngen,candidate/'generated',a.timeout,executable=binary)
    record={'configuration':config,'generation':generation,'status':'generated','correct':False,'rtl_path':str(rtl),'rtl_hash':file_hash(rtl) if rtl.exists() else None}
    write_json(candidate/'record.json',record)
    result={'case':path.stem,'correct':False,'generation':generation}
    if generation['returncode']==0:
        process=run([sys.executable,str(ROOT/'scripts/check_generic_verilator.py'),'--candidate-dir',str(candidate),'--output-dir',str(case/'verification'),'--externalize-control-roms','--timeout',str(a.timeout)],ROOT,case/'verification.log',a.timeout+120)
        result['verification_process']=process
        report=case/'verification/results.json'
        if report.exists():
            verified=json.loads(report.read_text());result.update(correct=process['returncode']==0 and verified['correct'],metrics=verified['metrics'],verification_sha256=file_hash(report))
    results.append(result);write_json(out/'results.json',{'correct':len(results)==len(campaigns) and all(r['correct'] for r in results),'completed':len(results),'expected':len(campaigns),'results':results})
    print(path.stem,'PASS' if result['correct'] else 'FAIL',flush=True)
raise SystemExit(0 if all(r['correct'] for r in results) else 1)
