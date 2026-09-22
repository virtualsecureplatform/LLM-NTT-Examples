"""Frozen-pool product policy replay with hidden implementation observations."""
import copy
import statistics
from . import product_search
from .model import digest,evidence_integrity,metric_number


def feasible(record):
    e=record.get('evidence',{}).get('synthesis',{})
    m=e.get('metrics',{})
    return (record.get('correct') is True and e.get('implementation_passed') is True
            and e.get('timing_clean') is True and metric_number(m.get('lut')) and m['lut']>=0
            and record.get('evaluation',{}).get('metrics',{}).get('initiation_interval_cycles',0)>0)


def frontier(records):
    candidates=[r for r in records if feasible(r)]
    def point(r):return (r['evidence']['synthesis']['metrics']['lut'],
                         r['evaluation']['metrics']['initiation_interval_cycles'])
    return [r for r in candidates if not any(all(a<=b for a,b in zip(point(s),point(r))) and
                 any(a<b for a,b in zip(point(s),point(r))) for s in candidates)]


def hypervolume(records,reference):
    points=sorted({(r['evidence']['synthesis']['metrics']['lut'],
                   r['evaluation']['metrics']['initiation_interval_cycles']) for r in frontier(records)})
    area=0;last=reference[1]
    for x,y in points:
        if x<reference[0] and y<last:area+=(reference[0]-x)*(last-y);last=y
    return area


def replay(report,budgets=(4,8,16),seeds=range(20),policies=('enumerate','random','analytical','cost')):
    pool=[r for r in report['candidates'] if r.get('correct') and r.get('status')!='duplicate']
    if not pool:raise ValueError('empty measured product pool')
    for r in pool:
        e=r.get('evidence',{}).get('synthesis')
        if not e or evidence_integrity(e)!='verified':raise ValueError('replay requires a fully accounted, verified synthesis pool')
    successful=[r for r in pool if feasible(r)]
    if not successful:raise ValueError('reference pool has no feasible synthesis point')
    reference=[1.1*max(r['evidence']['synthesis']['metrics']['lut'] for r in successful),
               1.1*max(r['evaluation']['metrics']['initiation_interval_cycles'] for r in successful)]
    truth={r['id']:r for r in pool};gold={r['id'] for r in frontier(pool)}
    full_hv=hypervolume(pool,reference);trials=[]
    for policy in policies:
        for seed in seeds:
            for budget in budgets:
                # Only configuration and cheap functional observations enter acquisition.
                remaining=[{k:copy.deepcopy(r[k]) for k in ('id','configuration','declared','evaluation') if k in r} for r in pool]
                observed=[];trace=[];first=None;errors=[]
                for step in range(min(budget,len(pool))):
                    chosen,prediction=product_search.choose(report['workload'],remaining,observed,policy,seed,step)
                    remaining.remove(chosen)
                    measured=truth[chosen['id']]
                    if prediction and 'lut' in prediction and measured['evidence']['synthesis'].get('implementation_passed'):
                        errors.append(abs(prediction['lut']-measured['evidence']['synthesis']['metrics']['lut']))
                    prior=[r['id'] for r in observed];observed.append(measured)
                    if first is None and feasible(measured):first=step+1
                    discovered={r['id'] for r in observed}&gold
                    trace.append(dict(step=step+1,candidate=chosen['id'],observed_before=prior,prediction=prediction,
                                      frontier_recall=len(discovered)/len(gold),
                                      hypervolume_fraction=hypervolume(observed,reference)/full_hv))
                trials.append(dict(policy=policy,seed=seed,budget=budget,evaluated=len(observed),
                                   first_feasible_evaluation=first,trace=trace,
                                   lut_prediction_mae=statistics.mean(errors) if errors else None,
                                   infeasible_evaluations=sum(not feasible(r) for r in observed)))
    return dict(schema='product-policy-replay-v1',workload=report['workload'],
                pool_sha256=digest(pool),reference_point=reference,reference_frontier=sorted(gold),trials=trials,
                limitation='Offline synthesis-stage replay; no routed throughput or live wall-time superiority claim.')


def ablations(report):
    """Report only actually measured one-factor pairs within a fixed workload."""
    axes=('backend','lanes','pe','radix','stage_groups','reduction','profile','fractional_bits','guard_bits','arithmetic')
    rows=[];records=[r for r in report['candidates'] if r.get('status')!='duplicate']
    for axis in axes:
        for i,left in enumerate(records):
            for right in records[i+1:]:
                a=left['configuration'];b=right['configuration']
                ignored={axis}|({'integer_bits'} if axis=='guard_bits' else set())
                if a.get(axis)==b.get(axis) or {k:v for k,v in a.items() if k not in ignored}!={k:v for k,v in b.items() if k not in ignored}:continue
                measurements={}
                for stage in ('synthesis','route'):
                    x=left.get('evidence',{}).get(stage,{});y=right.get('evidence',{}).get(stage,{})
                    if evidence_integrity(x)=='verified' and evidence_integrity(y)=='verified' and x.get('target')==y.get('target'):
                        measurements[stage]=dict(left=x,right=y)
                rows.append(dict(axis=axis,left=left['id'],right=right['id'],values=[a.get(axis),b.get(axis)],
                                 correctness=[left.get('correct'),right.get('correct')],
                                 status=[left['status'],right['status']],measurements=measurements))
    return dict(schema='product-ablations-v1',workload=report['workload'],pairs=rows,
                unmeasured_axes=[axis for axis in axes if not any(r['axis']==axis and r['measurements'] for r in rows)],
                limitation='Only one-factor pairs are attributed. Missing pairs and unmeasured axes are not inferred.')
