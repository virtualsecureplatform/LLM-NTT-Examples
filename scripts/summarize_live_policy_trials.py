#!/usr/bin/env python3
"""Score completed fresh policy trials against a complete matched measured pool."""
import argparse
import copy
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import canonical,file_hash,frontier,write_json
from architecture_search.constraints import bandwidth_bound
from architecture_search.replay import OBJECTIVES,validate_pool


def score_trial(reference, observed, target, limits, minimums=None,objectives=None):
    """Match artifacts/configurations, never assume independently assigned IDs match."""
    objectives=objectives or OBJECTIVES
    by_config={canonical(r['configuration']):r for r in reference}
    if len(by_config)!=len(reference):raise ValueError('duplicate reference configuration')
    normalized=[];seen=set();metric_differences=[]
    for record in observed:
        key=canonical(record['configuration'])
        if key not in by_config or key in seen:raise ValueError('unknown or repeated observed configuration')
        seen.add(key);matched=by_config[key]
        if record.get('correct') is True and (not record.get('rtl_hash') or record['rtl_hash']!=matched.get('rtl_hash')):
            raise ValueError('observed RTL differs from reference architecture')
        evidence=record.get('evidence',{}).get('synthesis')
        if evidence and evidence.get('target')!=target:raise ValueError('observation target differs from reference')
        item=copy.deepcopy(record);item['id']=matched['id'];normalized.append(item)
        actual=record.get('evidence',{}).get('synthesis',{}).get('metrics',{})
        expected=matched['evidence']['synthesis']['metrics']
        changes={k:{'reference':expected.get(k),'observed':actual.get(k)} for k in OBJECTIVES if expected.get(k)!=actual.get(k)}
        if changes:metric_differences.append({'configuration':record['configuration'],'metrics':changes})
    truth=frontier(reference,objectives,'synthesis',target,limits,minimums)
    recovered=frontier(normalized,objectives,'synthesis',target,limits,minimums)
    feasible=[r for r in normalized if frontier([r],objectives,'synthesis',target,limits,minimums)]
    return {'evaluations':len(observed),'failed_evaluations':sum(not r.get('correct') or r.get('evidence',{}).get('synthesis',{}).get('passed') is not True for r in observed),'reference_frontier_size':len(truth),'frontier_recall':len(set(truth)&set(recovered))/len(truth) if truth else None,
            'recovered_reference_ids':sorted(set(truth)&set(recovered)),'feasible_discoveries':len(feasible),
            'best_feasible_transforms_per_second':max((r['evidence']['synthesis']['metrics']['transforms_per_second'] for r in feasible),default=None),
            'measurement_differences':metric_differences}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-dir',type=Path,required=True)
    p.add_argument('--trials-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();inputs={}
    def read(path):
        inputs[str(path.resolve())]=file_hash(path)
        return json.loads(path.read_text())
    manifest=read(a.reference_dir/'manifest.json');campaign=manifest['campaign']
    reference_report=read(a.reference_dir/'report.json')
    trial_manifest=read(a.trials_dir/'manifest.json');results=read(a.trials_dir/'results.json')
    if trial_manifest['campaign']!=campaign or reference_report['workload']!=campaign['workload']:
        p.error('campaign/workload mismatch')
    expected={(policy,seed) for policy in trial_manifest['policies'] for seed in trial_manifest['seeds']}
    actual=[(t['policy'],t['seed']) for t in results['trials']]
    if len(actual)!=len(expected) or set(actual)!=expected:p.error('trial set is incomplete or duplicated')
    reference=validate_pool(reference_report,campaign['target'],'synthesis')
    if {canonical(r['configuration']) for r in reference}!={canonical(c) for c in manifest['configurations']}:
        p.error('reference pool does not cover the complete declared space')
    binary=manifest['identity']['ngen_binary']
    if {v for k,v in trial_manifest['inputs'].items() if k.endswith('/ngen.bat')}!={binary}:
        p.error('generator executable differs between reference and trials')
    objectives=OBJECTIVES.copy();minimums={}
    transport=bandwidth_bound(campaign['workload'],campaign.get('bandwidth',{}))
    if transport or campaign.get('requirements'):
        objectives['bandwidth_capped_transforms_per_second']=objectives.pop('transforms_per_second')
    required=campaign.get('requirements',{}).get('min_transforms_per_second')
    if required is not None:minimums['bandwidth_capped_transforms_per_second']=required
    rows=[]
    for trial in results['trials']:
        if trial['stop_reason'] is not None or trial['evaluations_completed']!=trial_manifest['evaluations_per_trial']:
            p.error('trial stopped or did not consume the equal evaluation budget')
        records=[]
        for step in trial['trace']:
            record=read(a.trials_dir/f"{trial['policy']}-{trial['seed']}"/'candidates'/step['candidate_id']/'record.json')
            if record.get('status') not in ('complete','hardware_failed','generation_failed','incorrect','error'):p.error('nonterminal or unscorable observation')
            metrics=record.get('evidence',{}).get('synthesis',{}).get('metrics',{})
            if 'transforms_per_second' in metrics:
                metrics['bandwidth_capped_transforms_per_second']=min(metrics['transforms_per_second'],transport['upper_transforms_per_second']) if transport else metrics['transforms_per_second']
            records.append(record)
        if len(records)!=trial['evaluations_completed']:p.error('trace/evaluation count mismatch')
        rows.append({'policy':trial['policy'],'seed':trial['seed'],'evaluations':len(records),
                     'elapsed_seconds':trial['elapsed_seconds'],'queue_seconds':sum(step.get('queue_seconds') or 0 for step in trial['trace']),
                     **score_trial(reference,records,campaign['target'],campaign.get('resource_limits',{}),minimums,objectives)})
    aggregate={}
    for policy in trial_manifest['policies']:
        samples=[r for r in rows if r['policy']==policy];values=[r['frontier_recall'] for r in samples if r['frontier_recall'] is not None]
        aggregate[policy]={'repetitions':len(samples),'mean_frontier_recall':statistics.mean(values) if values else None,
                           'min_frontier_recall':min(values) if values else None,'max_frontier_recall':max(values) if values else None}
    write_json(a.output,{'schema':'ntt-live-policy-comparison-v1','campaign':campaign,'trials':rows,'aggregate':aggregate,'inputs':inputs,
                        'limitations':'Same-workload synthesis experiment. Queue contention confounds wall time. Seeds control random/cost selection, not LLM backend randomness. Repetitions do not establish general policy superiority. Fresh measurement differences remain visible.'})
    print(a.output)

if __name__=='__main__':main()
