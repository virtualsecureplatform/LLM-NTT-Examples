"""Small empirical nearest-neighbor cost model with leave-one-out error reporting.

Predictions are advisory; they never become evidence or establish dominance.
"""
from __future__ import annotations
import math
from statistics import mean
from .model import metric_number


def distance(a: dict,b: dict) -> float:
    numeric=('pe','radix','lanes','stage_groups')
    return sum(abs(math.log2(a.get(k,1))-math.log2(b.get(k,1))) for k in numeric)+sum(a.get(k)!=b.get(k) for k in ('generator','backend','reduction','profile','transpose'))


def predict(samples: list[dict], configuration: dict, metric: str) -> dict:
    points=[p for p in samples if metric_number(p['metrics'].get(metric))]
    if not points:return {'available':False,'samples':0}
    neighbors=sorted(points,key=lambda p:distance(p['configuration'],configuration))[:3]
    weights=[1/(0.25+distance(p['configuration'],configuration)) for p in neighbors]
    values=[p['metrics'][metric] for p in neighbors]
    return {'available':True,'samples':len(points),'estimate':sum(w*v for w,v in zip(weights,values))/sum(weights),
            'neighbor_min':min(values),'neighbor_max':max(values)}


def calibrate(reports: list[dict],workload: dict,target: dict,stage='synthesis') -> dict:
    samples=[];seen=set()
    for report in reports:
        if report['workload']!=workload:continue
        for record in report['candidates']:
            evidence=record.get('evidence',{}).get(stage,{})
            identity=record.get('rtl_hash')
            if identity in seen or record.get('correct') is not True or evidence.get('target')!=target or not evidence.get('implementation_passed'):continue
            seen.add(identity)
            samples.append({'configuration':record['configuration'],'metrics':evidence['metrics'],'rtl_hash':identity})
    errors={}
    for metric in ('lut','ff','dsp','bram','uram','wns_ns'):
        pairs=[]
        if len(samples)>=3:
            for i,sample in enumerate(samples):
                estimate=predict(samples[:i]+samples[i+1:],sample['configuration'],metric)
                if estimate['available'] and metric_number(sample['metrics'].get(metric)):
                    pairs.append((estimate['estimate'],sample['metrics'][metric]))
        errors[metric]={'count':len(pairs),'mean_absolute_error':mean(abs(a-b) for a,b in pairs) if pairs else None}
    return {'schema':'ntt-cost-model-v1','method':'three nearest configurations, inverse-distance weights',
            'stage':stage,'workload':workload,'target':target,'samples':samples,'leave_one_out':errors,
            'limitation':'Same workload and target only; neighbor range is not a statistical confidence interval. No extrapolation safety guarantee.'}
