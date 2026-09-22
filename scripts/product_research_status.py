#!/usr/bin/env python3
"""Summarize milestone evidence without treating generated code as completed research."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import write_json

def summarize(root):
    def read(relative):
        p=root/relative
        return json.loads(p.read_text()) if p.is_file() else {}
    assurance=read('assurance.json');scale=read('scaled-hardware.json');freeze=read('search-freeze.json')
    pools=read('characterize.json');fresh=read('fresh.json');wide=read('wide/coverage.json');tfhe=read('wide/tfhe.json')
    scaled={int(name.split('-')[1]) for name,r in scale.get('campaigns',{}).items() if r.get('passed')}
    replays=[read(f'replay-{n}/replay.json') for n in (16,64,256)]
    board=[read(f'board/{gen}/evidence.json') for gen in ('ngen','sgen')]
    # M6 acceptance is deliberately a separate explicit artifact until every
    # preloaded adapter and both directions have measured evidence.
    baseline=read('autontt/matched-acceptance.json')
    states={
      'M1':dict(complete=assurance.get('complete') is True,required='130-point layered assurance matrix'),
      'M2':dict(complete=scaled=={16,64,256} and read('timing-repair.json').get('experiment_complete') is True,qualified_sizes=sorted(scaled)),
      'M3':dict(complete=bool(freeze) and pools.get('complete') is True and fresh.get('complete') is True and all(len(r.get('trials',[]))==240 for r in replays)),
      'M4':dict(complete=wide.get('complete') is True and tfhe.get('complete') is True),
      'M5':dict(complete=all(r.get('passed') is True for r in board)),
      'M6':dict(complete=baseline.get('passed') is True,required='measured matched AutoNTT adapters, ablations and portable evidence')}
    return dict(schema='product-research-status-v1',complete=all(s['complete'] for s in states.values()),milestones=states,
                scope='Summary of acceptance artifacts; inspect and verify the referenced campaign evidence before publication.')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args(argv)
    out=a.output_dir.resolve();result=summarize(out);write_json(out/'research-status.json',result)
    print(json.dumps(result,indent=2));return 0 if result['complete'] else 1
if __name__=='__main__':raise SystemExit(main())
