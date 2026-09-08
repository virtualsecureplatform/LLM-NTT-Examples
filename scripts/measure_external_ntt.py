#!/usr/bin/env python3
"""Measure a verified, normalized OpenNTT or Proteus stream with shared Vivado gates."""
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import hardware
from architecture_search.model import digest,file_hash,source_identity,write_json
from architecture_search.openntt import verified_record as openntt_record
from architecture_search.proteus import verified_record as proteus_record

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline-dir',type=Path,required=True)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--stage',choices=['synthesis','route'],default='synthesis')
p.add_argument('--timeout',type=float,default=3600)
a=p.parse_args();directory=a.baseline_dir.resolve();out=a.output_dir.resolve()
if not math.isfinite(a.timeout) or a.timeout<=0:p.error('timeout must be finite and positive')
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
c=json.loads(a.campaign.read_text());generator=json.loads((directory/'record.json').read_text())['generator']
if generator not in ('OpenNTT','Proteus'):p.error('unsupported external generator')
baseline=(openntt_record if generator=='OpenNTT' else proteus_record)(directory)
if baseline['workload']!=c['workload']:p.error('workload mismatch')
stream=json.loads((directory/'stream/results.json').read_text())
if not stream['correct'] or not stream.get('verification'):p.error('passing stream verification required')
if stream['boundary'].get('kind')!='registered-ready-valid' or stream['boundary'].get('lanes')!=c['workload']['lanes']:p.error('normalized boundary mismatch')
for name,expected in stream['verification'].items():
    if file_hash(Path(name))!=expected:p.error('verification artifact changed')
rtl=Path(stream['rtl'])
if file_hash(rtl)!=stream['rtl_hash']:p.error('verified wrapper changed')
rtl_sources=[Path(s) for s in stream['sources']]
# Every compiled core source must be one of the hash-checked generated artifacts.
for path in rtl_sources:
    if str(path.relative_to(directory)) not in baseline['artifacts']:p.error('untracked RTL source')
target={'part':'xcu280-fsvh2892-2L-e','tool_version':'2023.2','clock_period_ns':4.0,**c.get('target',{})}
identity={'baseline':baseline,'stream':stream,'target':target,'measurement_source':source_identity(Path(__file__).resolve().parents[1])}
key=digest(identity)
record={'id':key,'status':'running','correct':True,'configuration':{'generator':generator,**baseline['configuration'],'boundary':'registered-ready-valid'},
        'rtl_hash':stream['rtl_hash'],'provenance':identity,'evidence':{'simulation':{'passed':True,'target':target,'metrics':stream['metrics']}}}
write_json(out/'record.json',record)
result=hardware.evaluate(rtl,'SearchTop',target,stream['metrics'],out/a.stage,a.stage,a.timeout,rtl_sources,[directory/'hardware'])
record['evidence'][a.stage]=result;record['status']='complete';record['mode']=a.stage
record['measurement_artifacts']={str(f.relative_to(out)):file_hash(f) for f in (out/a.stage).glob('*') if f.is_file() and f.suffix in ('.rpt','.json','.tcl','.xdc','.txt','.properties')}
write_json(out/'record.json',record)
print(json.dumps({'passed':result['passed'],'metrics':result['metrics'],'record':str(out/'record.json')},indent=2))
raise SystemExit(0 if result['passed'] else 1)
