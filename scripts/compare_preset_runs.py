#!/usr/bin/env python3
"""Combine workload/target-matched preset reports without discarding failed points."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,write_json
from architecture_search.search import report
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--reports',type=Path,nargs='+',required=True)
p.add_argument('--output-dir',type=Path,required=True)
a=p.parse_args();out=a.output_dir.resolve();c=json.loads(a.campaign.read_text())
if c['workload'].get('kind')!='preset':p.error('preset workload required')
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
records={};artifacts={};inputs={}
for source in a.reports:
    data=json.loads(source.read_text());inputs[str(source.resolve())]=file_hash(source)
    if data['workload']!=c['workload']:p.error('workload mismatch')
    for record in data['candidates']:
        if record.get('status')=='running':p.error('report contains a running candidate')
        if record.get('rtl_path'):
            rtl=Path(record['rtl_path'])
            if not rtl.is_absolute():rtl=ROOT/rtl
            if file_hash(rtl)!=record['rtl_hash']:p.error('candidate RTL changed')
            artifacts[str(rtl)]=record['rtl_hash']
        for evidence in record.get('evidence',{}).values():
            if evidence.get('target')!=c['target']:p.error('target mismatch')
            for name,path in evidence.get('reports',{}).items():
                if not path or name=='build_dir':continue
                artifact=Path(path)
                if not artifact.is_absolute():artifact=ROOT/artifact
                if not artifact.is_file():p.error('missing hardware report artifact: '+str(artifact))
                artifacts[str(artifact)]=file_hash(artifact)
        key=record['id']
        if key in records and records[key]!=record:p.error('conflicting duplicate candidate')
        records[key]=record
for key,record in records.items():write_json(out/'candidates'/key/'record.json',record)
write_json(out/'manifest.json',{'schema':'ntt-preset-report-comparison-v1','campaign':c,'report_inputs':inputs,'artifact_hashes_at_import':artifacts,'runner_sha256':file_hash(Path(__file__)),'scope':'Matched original preset workload and target. Preserve failures; extra diagnostics do not redefine baseline qualification.'})
report(out,c);print(out/'report.json')
