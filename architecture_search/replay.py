"""Equal-evaluation-budget policy replay over a frozen, measured candidate pool.

Policies see legal configurations and only the measurements they have acquired.
The full pool is used solely by the evaluator to score frontier recovery.
"""
from __future__ import annotations
import random
import copy
from . import cost
from .model import canonical,evidence_integrity,frontier,metric_number

OBJECTIVES={'latency_ns':'min','transforms_per_second':'max','lut':'min','ff':'min','dsp':'min','bram':'min','uram':'min'}


def validate_pool(report: dict,target: dict,stage: str) -> list[dict]:
    records=report['candidates'];seen=set()
    if stage not in ('synthesis','route'):raise ValueError('replay requires measured hardware evidence')
    if len(records)<2:raise ValueError('at least two measured candidates are required')
    for r in records:
        key=canonical(r['configuration'])
        if key in seen:raise ValueError('duplicate configuration: do not mix architecture revisions in one replay')
        seen.add(key)
        e=r.get('evidence',{}).get(stage,{})
        if r.get('status') not in ('complete','hardware_failed') or r.get('mode')!='functional' or r.get('correct') is not True:
            raise ValueError('pool must contain completed, independently correct candidates')
        if evidence_integrity(e)=='invalid':raise ValueError('hardware evidence artifacts changed or are missing')
        if e.get('target')!=target or not e.get('implementation_passed'):
            raise ValueError('each candidate needs completed implementation under the same target')
        if any(not metric_number(e.get('metrics',{}).get(k)) for k in OBJECTIVES):
            raise ValueError('missing hardware objective in replay pool')
    return records


def score(observed: list[dict],records: list[dict],stage: str,target: dict,limits: dict,objectives=None,minimums=None) -> dict:
    reference=frontier(records,objectives or OBJECTIVES,stage,target,limits,minimums)
    recovered=frontier(observed,objectives or OBJECTIVES,stage,target,limits,minimums)
    return {'reference_frontier_size':len(reference),'recovered_reference_ids':[i for i in reference if i in recovered],
            'frontier_recall':len(set(reference)&set(recovered))/len(reference) if reference else None,
            'feasible_discoveries':sum(bool(frontier([r],objectives or OBJECTIVES,stage,target,limits,minimums)) for r in observed),
            'observed_frontier_ids':recovered}


def trial(records: list[dict],target: dict,stage: str,budget: int,policy: str,seed: int,
          limits: dict | None=None,llm_order: list[dict] | None=None,objectives=None,minimums=None,llm_selector=None) -> dict:
    if policy not in ('enumerate','random','cost','llm'):raise ValueError('unknown replay policy')
    if not 1<=budget<=len(records):raise ValueError('budget must be within the measured pool size')
    rng=random.Random(seed);remaining=sorted(records,key=lambda r:canonical(r['configuration']))
    if policy in ('random','cost'):rng.shuffle(remaining)
    if policy=='llm' and llm_selector is None:
        if llm_order is None:raise ValueError('LLM order required')
        rank={canonical(c):i for i,c in enumerate(llm_order)}
        if len(rank)!=len(records) or set(rank)!={canonical(r['configuration']) for r in records}:raise ValueError('LLM order must be an exact legal permutation')
        remaining.sort(key=lambda r:rank[canonical(r['configuration'])])
    observed=[];samples=[];trace=[];errors=[]
    for step in range(budget):
        prediction=None
        if policy=='llm' and llm_selector is not None:
            history=[{'configuration':r['configuration'],'correct':r.get('correct') is True,
                      'implementation_passed':r['evidence'][stage].get('implementation_passed') is True,
                      'timing_passed':r['evidence'][stage].get('passed') is True,
                      'metrics':r['evidence'][stage]['metrics']} for r in observed]
            # Copy only acquired observations and legal configurations across
            # the policy boundary. Hidden metrics and reference IDs stay here.
            selected=llm_selector(copy.deepcopy([r['configuration'] for r in remaining]),copy.deepcopy(history),step)
            matches=[r for r in remaining if canonical(r['configuration'])==canonical(selected)]
            if len(matches)!=1:raise ValueError('LLM selected an unknown or already observed configuration')
            candidate=matches[0];remaining.remove(candidate)
        elif policy=='cost' and samples and step%4!=3:
            ranked=[(cost.predict(samples,r['configuration'],'lut'),i,r) for i,r in enumerate(remaining)]
            prediction,_,candidate=min(ranked,key=lambda row:(row[0]['estimate'],row[1]))
            remaining.remove(candidate)
        else:candidate=remaining.pop(0)
        # Only now reveal this candidate's outcome to the policy.
        observed.append(candidate);e=candidate['evidence'][stage]
        samples.append({'configuration':candidate['configuration'],'metrics':e['metrics'],'rtl_hash':candidate.get('rtl_hash')})
        if prediction:errors.append(abs(prediction['estimate']-e['metrics']['lut']))
        trace.append({'step':step+1,'candidate_id':candidate['id'],'implementation_timing_passed':e.get('passed') is True,
                      'lut_prediction_before_measurement':prediction,**score(observed,records,stage,target,limits or {},objectives,minimums)})
    return {'policy':policy,'seed':seed,'budget':budget,'trace':trace,'final':trace[-1],
            'online_lut_prediction_mae':sum(errors)/len(errors) if errors else None,'prediction_count':len(errors)}
