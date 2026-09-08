#!/usr/bin/env python3
"""Build a workload-matched frontier from verified NGen and normalized OpenNTT runs."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import digest,file_hash,write_json
from architecture_search.openntt import verified_record
from architecture_search.search import report

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--ngen-report',type=Path,required=True)
p.add_argument('--openntt-dirs',type=Path,nargs='+',required=True)
p.add_argument('--output-dir',type=Path,required=True)
a=p.parse_args();c=json.loads(a.campaign.read_text());ngen=json.loads(a.ngen_report.read_text())
if ngen['workload']!=c['workload']:p.error('NGen workload differs from comparison workload')
if a.output_dir.exists() and any(a.output_dir.iterdir()):p.error('output directory must be empty')
records=list(ngen['candidates'])
for path in a.openntt_dirs:
    path=path.resolve();baseline=verified_record(path)
    if baseline['workload']!=c['workload']:p.error('OpenNTT workload differs from comparison workload')
    result=json.loads((path/'stream/results.json').read_text())
    if not result['correct']:p.error('OpenNTT stream correctness failed')
    if not result.get('verification'):p.error('OpenNTT verification provenance missing; rerun the stream check')
    for verification_path,expected_hash in result['verification'].items():
        if file_hash(Path(verification_path))!=expected_hash:p.error('OpenNTT verification artifact changed')
    if file_hash(Path(result['rtl']))!=result['rtl_hash']:p.error('OpenNTT wrapper changed after verification')
    expected_boundary={'kind':'registered-ready-valid','lanes':c['workload']['lanes'],'adapter_coefficient_buffers':2,'host_coefficients_per_cycle':1}
    if result['boundary']!=expected_boundary:p.error('OpenNTT boundary is not normalized')
    key=digest({'baseline':baseline,'stream':result})
    records.append({'id':key,'status':'complete','correct':True,'mode':'functional','rtl_hash':result['rtl_hash'],
                    'configuration':{'generator':'OpenNTT',**baseline['configuration'],'boundary':'registered-ready-valid'},
                    'provenance':{'baseline':baseline,'stream':result},
                    'evidence':{'simulation':{'passed':True,'target':c['target'],'metrics':result['metrics']}}})
for record in records:
    if record.get('evidence',{}).get('simulation',{}).get('target')!=c['target']:p.error('target contract mismatch')
    write_json(a.output_dir/'candidates'/record['id']/'record.json',record)
write_json(a.output_dir/'manifest.json',{'schema':'ntt-comparison-v1','campaign':c,'ngen_report_sha256':file_hash(a.ngen_report),'openntt_dirs':[str(p.resolve()) for p in a.openntt_dirs],'scope':'Normalized streaming simulation; resource and routed frontiers require corresponding measured evidence.'})
report(a.output_dir,c)
print(a.output_dir/'report.md')
