"""Sequential legal-configuration acquisition, using only previously observed data."""
import random
from . import cost
from .model import canonical,metric_number


def choose(remaining,observed,method,seed,step):
    if method not in ('enumerate','random','cost'):raise ValueError('unknown acquisition policy')
    ordered=sorted(remaining,key=canonical)
    if not ordered:raise ValueError('empty acquisition space')
    if method=='enumerate':return ordered[0],None
    rng=random.Random(seed);rng.shuffle(ordered)
    if method=='random':return ordered[0],None
    samples=[{'configuration':r['configuration'],'metrics':r['metrics']} for r in observed if metric_number(r.get('metrics',{}).get('lut'))]
    if not samples or step%4==3:return ordered[0],None
    ranked=[(cost.predict(samples,c,'lut'),i,c) for i,c in enumerate(ordered)]
    prediction,_,selected=min(ranked,key=lambda row:(row[0]['estimate'],row[1]))
    return selected,prediction
