#!/usr/bin/env python3
"""Characterize product pools, replay classical policies, or run fresh trials."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import release,research,product_study
from architecture_search.model import write_json,file_hash,evidence_integrity
from architecture_search.search import main as search_main,report as search_report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',required=True,choices=['characterize','replay','fresh','ablations'])
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--sizes',type=int,nargs='+',default=[16,64,256])
    p.add_argument('--report',type=Path)
    p.add_argument('--resume',action='store_true')
    a=p.parse_args(argv);out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.stage in ('replay','ablations'):
        if a.report is None:p.error('--report is required for replay')
        result=getattr(product_study,a.stage)(json.loads(a.report.read_text()))
        result['report_sha256']=file_hash(a.report);write_json(out/(a.stage+'.json'),result);return 0
    campaigns=[]
    if a.stage=='characterize':
        for n in a.sizes:
            if n==256:
                if not (out/'search-freeze.json').exists():p.error('freeze search settings in this output directory before N=256')
                research.freeze_search(out)
            c=release.campaign(n,matrix=True,hardware=True,period=8)
            c['stages']=['simulation','synthesis'];c['budget'].update(hours=48,synthesis=len(c['space']['configurations']),route=0)
            campaigns.append((f'pool-{n}','enumerate',0,c))
    else:
        for seed in range(3):
            # Rotate policy order to reduce systematic ordering effects.
            policies=['enumerate','random','analytical','cost'];policies=policies[seed:]+policies[:seed]
            for policy in policies:
                c=release.campaign(64,matrix=True,hardware=True,period=8)
                c['stages']=['simulation','synthesis'];c['budget'].update(hours=6,synthesis=4,route=0)
                campaigns.append((f'fresh-{policy}-{seed}',policy,seed,c))
    index=out/(a.stage+'.json')
    results=json.loads(index.read_text()).get('campaigns',{}) if index.exists() else {}
    for name,policy,seed,c in campaigns:
        path=out/(name+'.json');directory=out/name
        if path.exists() and json.loads(path.read_text())!=c:raise ValueError('campaign definition changed')
        write_json(path,c)
        mode='resume' if a.resume and (directory/'manifest.json').exists() else 'run'
        code=search_main(['--campaign',str(path),'--output-dir',str(directory),'--mode',mode,'--policy',policy,'--seed',str(seed)])
        r=search_report(directory,c)
        measured=sum('synthesis' in x.get('evidence',{}) for x in r['candidates'])
        expected=(sum(x.get('correct') and x.get('status')!='duplicate' for x in r['candidates'])
                  if a.stage=='characterize' else 4)
        verified=sum(evidence_integrity(x.get('evidence',{}).get('synthesis',{}))=='verified' for x in r['candidates'])
        complete=measured==verified==expected and expected>0 and release.accept(r,c)['passed']
        results[name]=dict(complete=complete,exit_code=code,measured=measured,verified=verified,required=expected,report=str(directory/'report.json'))
        required=({f'pool-{n}' for n in (16,64,256)} if a.stage=='characterize' else
                  {f'fresh-{policy}-{seed}' for policy in ('enumerate','random','analytical','cost') for seed in range(3)})
        write_json(index,dict(complete=required<=set(results) and all(results[name]['complete'] for name in required),campaigns=results))
        if not complete:return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
