#!/usr/bin/env python3
"""Verify published SEAL trace samples independently of the SEAL installation."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.capture_seal_ntt_trace import verify_samples
from architecture_search.model import file_hash

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--samples-dir',type=Path,required=True);a=p.parse_args()
    report=json.loads(a.report.read_text());events_path=a.samples_dir/'events.jsonl'
    if report.get('correct') is not True or report.get('schema')!='ntt-seal-ckks-trace-v1' or len(report.get('samples',[]))!=8 or not report.get('events'):raise ValueError('complete successful CKKS capture required')
    if file_hash(events_path)!=report['inputs']['events_sha256']:raise ValueError('event file changed')
    events=[json.loads(line) for line in events_path.read_text().splitlines()]
    if events!=report['events']:raise ValueError('events differ from report')
    samples=verify_samples(a.samples_dir,events)
    if samples!=report['samples']:raise ValueError('sample hashes or oracle results differ')
    print(json.dumps({'correct':True,'calls':len(events),'samples':len(samples)}))
if __name__=='__main__':main()
