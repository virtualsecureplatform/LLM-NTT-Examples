#!/usr/bin/env python3
"""Emit the paper/FHE/PQC suite with exact fields and verified SEAL trace linkage."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.benchmark_suite import campaign,definitions,polynomial_product_check
from architecture_search.model import file_hash,write_json
from scripts.capture_seal_ntt_trace import verify_samples
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seal-trace',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    out=a.output_dir
    if out.exists() and any(out.iterdir()):p.error('use a fresh output directory')
    trace=json.loads(a.seal_trace.read_text())
    samples_dir=a.seal_trace.resolve().parent/'trace'
    events_file=samples_dir/'events.jsonl'
    if file_hash(events_file)!=trace['inputs']['events_sha256']:raise ValueError('trace event file changed')
    events=[json.loads(line) for line in events_file.read_text().splitlines()]
    if events!=trace['events'] or verify_samples(samples_dir,events)!=trace['samples']:raise ValueError('captured sample evidence differs')
    cases=definitions(trace);rows=[]
    for case in cases:
        if not polynomial_product_check(case['domain'],case['negacyclic']):raise ValueError('polynomial oracle mismatch: '+case['name'])
        row={**case,'polynomial_product_oracle_passed':True,'campaigns':{}}
        for direction in ('forward','inverse'):
            name=case['name']+'-'+direction+'.json'
            for kind,validation in [('validation',True),('search',False)]:
                path=out/kind/name;write_json(path,campaign(case,direction,validation));row['campaigns'][kind+'-'+direction]={'path':str(path.relative_to(out)),'sha256':file_hash(path)}
        rows.append(row)
    # Existing dedicated implementation handles ML-KEM's incomplete transform.
    kyber=json.loads((ROOT/'campaigns/kyber.json').read_text());kyber['space']['backends']=['compact'];kyber['benchmark']={'name':'mlkem256','n':256,'q':'3329','algorithm':'incomplete NTT and quadratic base multiplication','source':'https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf','scope':'Dedicated Kyber preset/oracle. Never passed to the full negacyclic generic adapter.'};write_json(out/'preset/mlkem256.json',kyber)
    write_json(out/'suite.json',{'schema':'ntt-realistic-benchmarks-v1','cases':rows,'preset':{'path':'preset/mlkem256.json','sha256':file_hash(out/'preset/mlkem256.json')},'application_trace':{'source':str(a.seal_trace.resolve()),'sha256':file_hash(a.seal_trace),'calls':len(trace['events']),'seal_revision':trace['seal_revision']},'methodology':{'directions':['forward','inverse'],'traffic':['single frame','back-to-back frames','input gaps','output backpressure'],'primary_metrics':['routed setup and hold','LUT','FF','DSP','BRAM','URAM','transaction cycles','frame interval','transfer-inclusive throughput'],'holdout_rule':'Freeze policy/settings before measuring 16K/64K FHE outcomes; initial correctness tests do not supply PPA observations.','scope':'Workload templates and mathematical checks; hardware qualification comes only from separate measured reports.'}})
    print(out/'suite.json')
if __name__=='__main__':main()
