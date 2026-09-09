#!/usr/bin/env python3
"""Compare policies at equal measurement budgets over a frozen hardware-evaluated pool."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import policy,replay,constraints
from architecture_search.model import file_hash,source_identity,write_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--report',type=Path,required=True)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--stage',choices=['synthesis','route'],default='synthesis')
p.add_argument('--budget',type=int,required=True)
p.add_argument('--seeds',type=int,nargs='+',default=[1,2,3,4,5])
p.add_argument('--llm',action='store_true')
p.add_argument('--sequential-llm',action='store_true',help='Re-rank after each acquired observation; implies --llm')
p.add_argument('--llm-timeout',type=float,default=180)
a=p.parse_args();a.llm=a.llm or a.sequential_llm;report=json.loads(a.report.read_text());campaign=json.loads(a.campaign.read_text())
if report['workload']!=campaign['workload'] or report['workload'].get('kind')!='generic':p.error('matching generic workload required')
if a.output_dir.exists() and any(a.output_dir.iterdir()):p.error('output directory must be empty')
records=replay.validate_pool(report,campaign['target'],a.stage)
for record in records:
    constraints.analyze(campaign['workload'],record['configuration'],campaign['target'],campaign.get('bandwidth'),campaign.get('requirements'))
objectives=dict(replay.OBJECTIVES);minimums={}
transport=constraints.bandwidth_bound(campaign['workload'],campaign.get('bandwidth',{}))
if transport or campaign.get('requirements'):
    objectives['bandwidth_capped_transforms_per_second']=objectives.pop('transforms_per_second')
    for r in records:
        metrics=r['evidence'][a.stage]['metrics'];rate=metrics['transforms_per_second']
        metrics['bandwidth_capped_transforms_per_second']=min(rate,transport['upper_transforms_per_second']) if transport else rate
    required=campaign.get('requirements',{}).get('min_transforms_per_second')
    if required is not None:minimums={'bandwidth_capped_transforms_per_second':required}

if not 1<=a.budget<=len(records):p.error('budget must be within the measured pool size')
a.output_dir.mkdir(parents=True)
manifest={'schema':'ntt-policy-replay-v1','report_sha256':file_hash(a.report),'report':str(a.report.resolve()),'campaign':campaign,
          'stage':a.stage,'budget':a.budget,'seeds':a.seeds,'source':source_identity(Path(__file__).resolve().parents[1]),
          'policies':{'enumerate':'canonical configuration order','random':'seeded permutation','cost':'online nearest-neighbor LUT acquisition with every fourth step reserved for exploration; differs from the CLI static pretrained cost ranking','llm':('sequential legal-ID ranking with acquired observations only' if a.sequential_llm else 'static legal-ID ranking from configurations and constraints, without hidden metrics')},
          'limitation':'Offline finite-pool replay with equal candidate counts. Does not measure end-to-end search time or generalization beyond the pool.'}
write_json(a.output_dir/'manifest.json',manifest)
trials=[];failures=[]
for seed in a.seeds:
    methods=['enumerate','random','cost'];order=None
    if a.llm and not a.sequential_llm:
        directory=a.output_dir/f'llm-{seed}';directory.mkdir()
        try:
            order=policy.rank([r['configuration'] for r in records],campaign['workload'],{**campaign.get('llm',{}),'target':campaign['target'],'resource_limits':campaign.get('resource_limits',{}),'objectives':objectives,'requirements':campaign.get('requirements',{}),'bandwidth':campaign.get('bandwidth',{})},directory,a.llm_timeout)
            methods.append('llm')
        except Exception as error:
            failures.append({'seed':seed,'policy':'llm','error':str(error)})
            # An endpoint failure is not relabeled as an LLM result.
    if a.sequential_llm:
        def select(remaining,observed,step):
            directory=a.output_dir/f'llm-{seed}'/f'step-{step+1}';directory.mkdir(parents=True)
            return policy.rank(remaining,campaign['workload'],{**campaign.get('llm',{}),'target':campaign['target'],
                'resource_limits':campaign.get('resource_limits',{}),'objectives':objectives,
                'requirements':campaign.get('requirements',{}),'bandwidth':campaign.get('bandwidth',{}),
                'observations':observed,'evaluations_remaining':a.budget-step},directory,a.llm_timeout)[0]
        try:
            trials.append(replay.trial(records,campaign['target'],a.stage,a.budget,'llm',seed,campaign.get('resource_limits',{}),
                                      objectives=objectives,minimums=minimums,llm_selector=select))
        except Exception as error:
            failures.append({'seed':seed,'policy':'llm','error':str(error)})
    for method in methods:
        trials.append(replay.trial(records,campaign['target'],a.stage,a.budget,method,seed,campaign.get('resource_limits',{}),order,objectives,minimums))
    write_json(a.output_dir/'results.json',{'trials':trials,'failures':failures})
lines=['# Equal-budget policy replay','','Offline measurements; no wall-time or unseen-design claim.','',
       '| Policy | Seed | Evaluations | Frontier recall | Feasible discoveries | Online LUT MAE |','| --- | ---: | ---: | ---: | ---: | ---: |']
for t in trials:
    f=t['final'];lines.append(f"| {t['policy']} | {t['seed']} | {t['budget']} | {f['frontier_recall']} | {f['feasible_discoveries']} | {t['online_lut_prediction_mae']} |")
if failures:lines+=['',f'LLM failures: {len(failures)}; recorded separately in results.json.']
(a.output_dir/'report.md').write_text('\n'.join(lines)+'\n')
print(a.output_dir/'report.md')
