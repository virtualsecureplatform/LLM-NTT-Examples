#!/usr/bin/env python3
"""Run sequential acquisition with fresh correctness and hardware evaluations."""
import argparse
import json
import math
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import acquisition,adapters,constraints,oracle,policy
from architecture_search.model import canonical,file_hash,run,source_identity,write_json
from architecture_search.search import report

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--policies',nargs='+',choices=['enumerate','random','cost','llm'],default=['enumerate','random','cost','llm'])
p.add_argument('--seeds',nargs='+',type=int,default=[1])
p.add_argument('--evaluations',type=int,default=2)
p.add_argument('--hours',type=float,default=12)
p.add_argument('--ngen-root',type=Path,default=ROOT.parent/'NGen')
a=p.parse_args();campaign=json.loads(a.campaign.read_text());out=a.output_dir.resolve();ngen=a.ngen_root.resolve()
if campaign['workload'].get('kind')!='generic':p.error('live trials currently require a generic workload')
oracle.validate(campaign['workload'])
if campaign.get('stages')!=['simulation','synthesis']:p.error('live trials currently require simulation followed by synthesis')
if not math.isfinite(a.hours) or a.hours<=0 or a.evaluations<1:p.error('positive time/evaluation budgets required')
if len(a.policies)!=len(set(a.policies)) or len(a.seeds)!=len(set(a.seeds)):p.error('policies and seeds must be unique')
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
legal=adapters.candidates(campaign['workload'],ngen,campaign.get('space'))
legal=[c for c in legal if not constraints.analyze(campaign['workload'],c,campaign['target'],campaign.get('bandwidth'),campaign.get('requirements'))['pruned']]
if a.evaluations>len(legal):p.error('evaluation budget exceeds remaining legal space')
# Hash executable inputs, separately from documentation or unrelated build artifacts.
def inputs():
    paths=list((ROOT/'architecture_search').glob('*.py'))+[ROOT/'scripts/search_architectures.py',Path(__file__).resolve(),ROOT/'scripts/vitis_synth_rtl.sh',ROOT/'scripts/insert_output_hold_buffers.tcl',ngen/'ngen.bat']
    return {str(path):file_hash(path) for path in paths}
identity=inputs();out.mkdir(parents=True);started=time.monotonic()
write_json(out/'manifest.json',{'schema':'ntt-live-policy-trials-v1','campaign':campaign,'source':source_identity(ROOT),'ngen_source':source_identity(ngen),'inputs':identity,'policies':a.policies,'seeds':a.seeds,'evaluations_per_trial':a.evaluations,'hours_total':a.hours,'limitation':'Fresh per-policy evaluations, no cross-policy measurement reuse. Queue time is recorded and may confound elapsed-time comparisons. No unseen-design frontier recall without a complete reference pool.'})
trials=[]
for seed in a.seeds:
    for method in a.policies:
        trialdir=out/f'{method}-{seed}';trialdir.mkdir();remaining=list(legal);observed=[];trace=[];reason=None
        trial_start=time.monotonic()
        for step in range(a.evaluations):
            budget=a.hours*3600-(time.monotonic()-started)
            if budget<=0:reason='total wall-time budget exhausted';break
            if inputs()!=identity:reason='executable input changed; start a new trial campaign';break
            work=trialdir/f'step-{step+1}';work.mkdir();prediction=None;selection_start=time.monotonic()
            if method=='llm':
                try:
                    ranked=policy.rank(remaining,campaign['workload'],{**campaign.get('llm',{}),'target':campaign['target'],'resource_limits':campaign.get('resource_limits',{}),'requirements':campaign.get('requirements',{}),'bandwidth':campaign.get('bandwidth',{}),'observations':observed},work,min(180,budget))
                    selected=ranked[0]
                except Exception as error:
                    reason='LLM acquisition failed: '+str(error);write_json(work/'acquisition-failure.json',{'error':reason});break
            else:selected,prediction=acquisition.choose(remaining,observed,method,seed,step)
            selection_seconds=time.monotonic()-selection_start
            remaining.remove(selected);write_json(work/'configuration.json',selected)
            child={**campaign,'budget':{'hours':max(0,(a.hours*3600-(time.monotonic()-started))/3600),'functional':1,'synthesis':1,'route':0}}
            write_json(work/'campaign.json',child)
            process=run([sys.executable,str(ROOT/'scripts/search_architectures.py'),'--campaign',str(work/'campaign.json'),'--configuration-json',str(work/'configuration.json'),'--ngen-root',str(ngen),'--output-dir',str(work/'evaluation'),'--mode','run'],ROOT,work/'evaluation.log',max(0,a.hours*3600-(time.monotonic()-started)))
            reportpath=work/'evaluation/report.json';records=json.loads(reportpath.read_text())['candidates'] if reportpath.exists() else []
            if len(records)!=1:
                reason='evaluation did not produce exactly one candidate record';trace.append({'step':step+1,'configuration':selected,'process':process,'failure':reason});break
            candidate=records[0];hardware=candidate.get('evidence',{}).get('synthesis',{})
            observation={'configuration':selected,'correct':candidate.get('correct') is True,'implementation_passed':hardware.get('implementation_passed') is True,'timing_passed':hardware.get('passed') is True,'metrics':hardware.get('metrics',{})}
            observed.append(observation)
            write_json(trialdir/'candidates'/candidate['id']/'record.json',candidate)
            summary=report(trialdir,campaign)
            trace.append({'step':step+1,'candidate_id':candidate['id'],'configuration':selected,'selection_seconds':selection_seconds,'prediction_before_measurement':prediction,'observation':observation,'queue_seconds':hardware.get('queue_seconds'),'process':process,'report_sha256':file_hash(reportpath),'synthesis_frontier':summary['frontiers']['synthesis'],'elapsed_seconds':time.monotonic()-trial_start})
            write_json(trialdir/'trace.json',trace)
            print(method,seed,step+1,candidate['status'],flush=True)
        trial={'policy':method,'seed':seed,'evaluations_completed':len(observed),'requested_evaluations':a.evaluations,'elapsed_seconds':time.monotonic()-trial_start,'stop_reason':reason,'trace':trace}
        trials.append(trial);write_json(out/'results.json',{'trials':trials,'elapsed_seconds':time.monotonic()-started})
        if reason=='executable input changed; start a new trial campaign':raise SystemExit(reason)
print(out/'results.json')
raise SystemExit(0 if all(t['evaluations_completed']==a.evaluations for t in trials) else 1)
