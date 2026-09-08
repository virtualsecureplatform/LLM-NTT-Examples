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


def predict(samples: list[dict], configuration: dict, metric: str, method: str='nearest') -> dict:
    if method=='structural':return structural_predict(samples,configuration,metric)
    if method!='nearest':raise ValueError('unknown cost method')
    points=[p for p in samples if metric_number(p['metrics'].get(metric))]
    if not points:return {'available':False,'samples':0}
    neighbors=sorted(points,key=lambda p:distance(p['configuration'],configuration))[:3]
    weights=[1/(0.25+distance(p['configuration'],configuration)) for p in neighbors]
    values=[p['metrics'][metric] for p in neighbors]
    return {'available':True,'samples':len(points),'estimate':sum(w*v for w,v in zip(weights,values))/sum(weights),
            'neighbor_min':min(values),'neighbor_max':max(values)}


def calibrate(reports: list[dict],workload: dict,target: dict,stage='synthesis',method='nearest') -> dict:
    if method not in ('nearest','structural'):raise ValueError('unknown cost method')
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
                estimate=predict(samples[:i]+samples[i+1:],sample['configuration'],metric,method)
                if estimate['available'] and metric_number(sample['metrics'].get(metric)):
                    pairs.append((estimate['estimate'],sample['metrics'][metric]))
        errors[metric]={'count':len(pairs),'mean_absolute_error':mean(abs(a-b) for a,b in pairs) if pairs else None}
    return {'schema':'ntt-cost-model-v1','method':method,'method_description':('three nearest configurations, inverse-distance weights' if method=='nearest' else 'least squares: fixed overhead + stage groups + PE times stage groups; matching radix-2 streamed family only'),
            'stage':stage,'workload':workload,'target':target,'samples':samples,'leave_one_out':errors,
            'limitation':'Same workload and target only; neighbor range is not a statistical confidence interval. No extrapolation safety guarantee.'}


def structural_predict(samples: list[dict], configuration: dict, metric: str) -> dict:
    """Fit physical replication terms; unavailable for unsupported or rank-deficient data.

    This is an empirical estimate, never a lower bound or a pruning certificate.
    """
    unavailable={'available':False,'samples':0,'method':'structural'}
    if metric not in ('lut','ff','dsp','bram','uram') or configuration.get('backend')!='streamed' or configuration.get('radix')!=2:
        return {**unavailable,'reason':'unsupported architecture or metric'}
    def family(c):return {k:v for k,v in c.items() if k not in ('pe','stage_groups')}
    points=[p for p in samples if family(p['configuration'])==family(configuration) and metric_number(p['metrics'].get(metric))]
    unavailable['samples']=len(points)
    if len(points)<3:return {**unavailable,'reason':'at least three matching observations required'}
    def features(c):
        pe=c.get('pe',1);groups=c.get('stage_groups',1)
        if not metric_number(pe) or not metric_number(groups) or pe<=0 or groups<=0:raise ValueError('positive PE and stage group counts required')
        return [1.0,float(groups),float(pe*groups)]
    rows=[features(p['configuration']) for p in points];values=[p['metrics'][metric] for p in points]
    # Three-column normal equations with pivoting. Refuse underdetermined fits.
    matrix=[[sum(x[i]*x[j] for x in rows) for j in range(3)]+[sum(x[i]*y for x,y in zip(rows,values))] for i in range(3)]
    scale=max(abs(v) for row in matrix for v in row[:3])
    for col in range(3):
        pivot=max(range(col,3),key=lambda i:abs(matrix[i][col]))
        if abs(matrix[pivot][col])<=1e-10*max(1,scale):return {**unavailable,'reason':'rank-deficient replication features'}
        matrix[col],matrix[pivot]=matrix[pivot],matrix[col]
        divisor=matrix[col][col];matrix[col]=[v/divisor for v in matrix[col]]
        for i in range(3):
            if i!=col:
                factor=matrix[i][col];matrix[i]=[v-factor*w for v,w in zip(matrix[i],matrix[col])]
    coefficients=[row[3] for row in matrix]
    estimate=sum(a*b for a,b in zip(features(configuration),coefficients))
    return {'available':True,'samples':len(points),'method':'structural','estimate':max(0.0,estimate),
            'unclipped_estimate':estimate,'coefficients':dict(zip(('fixed','groups','pe_groups'),coefficients)),
            'limitation':'Empirical replication fit, not a safe bound; no timing prediction.'}
