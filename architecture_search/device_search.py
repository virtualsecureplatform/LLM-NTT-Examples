"""Calibrated resource acquisition for a fixed, independently qualified pool."""
import math
import random
from .device import RESOURCES, limits, performance


def family(row):
    c = row['configuration']
    return c['generator'] + ':' + c['backend'] + (':'+c['product_profile'] if c.get('product_profile','baseline')!='baseline' else '')


def features(row):
    c = row['configuration']
    return dict(cells=max(1,row['yosys_cells']),ff=max(1,row['register_bits']),
                dsp=max(1,row['multipliers']),memory=max(1,row['memory_bits']),
                n=row['workload']['n'],lanes=c['lanes'],pe=c.get('pe',1),groups=c.get('stage_groups',1),
                width=c.get('integer_bits',0)+c.get('fractional_bits',0),radix=c['radix'])


def distance(a,b):
    fa,fb=features(a),features(b)
    return sum(abs(math.log2(1+fa[k])-math.log2(1+fb[k])) for k in fa)


def predict(row, observed):
    samples = [(r,e) for r,e in observed if family(r)==family(row) and e.get('passed')
               and all(k in e.get('metrics',{}) for k in RESOURCES)]
    if not samples:
        return dict(method='uncalibrated',resources=None,samples=0)
    neighbors = sorted(samples,key=lambda pair:(distance(row,pair[0]),pair[0]['name']))[:3]
    proxies = dict(lut='cells',ff='ff',dsp='dsp',bram36='memory',uram='memory')
    weights = [1/(.25+distance(row,r)) for r,e in neighbors]
    f = features(row)
    resources = {k:sum(weight*e['metrics'][k]*f[proxies[k]]/features(r)[proxies[k]]
                       for weight,(r,e) in zip(weights,neighbors))/sum(weights) for k in RESOURCES}
    return dict(method='family-nearest-scaled-v1',resources=resources,samples=len(samples),
                neighbors=[r['name'] for r,e in neighbors],
                limitation='empirical estimate; no confidence or feasibility guarantee')


def calibration_split(rows):
    calibration,heldout=[],[]
    for workload in sorted({r['workload_name'] for r in rows}):
        group=[r for r in rows if r['workload_name']==workload]
        for f in sorted({family(r) for r in group}):
            exact=[r for r in group if family(r)==f and r['max_abs_error']==0 and not r['quant_bits']]
            if not exact: continue
            def key(r):
                c=r['configuration']
                preferred_lanes=4 if c['backend'] in ('stage-parallel','full-throughput') else 2
                return (c['lanes']!=preferred_lanes,c.get('pe',1)!=1,c['radix']!=2,
                        c.get('stage_groups',1)!=1,c.get('reduction','barrett')!='barrett',
                        c.get('fractional_bits',30)!=30,c.get('guard_bits',0),r['name'])
            calibration.append(min(exact,key=key)['name'])
        remaining=[r for r in group if r['name'] not in calibration]
        # Hold out one distinct NTT and FFT architecture/precision case per workload.
        for generator in ('ngen','sgen'):
            options=[r for r in remaining if r['configuration']['generator']==generator]
            if not options: continue
            def key(r):
                c=r['configuration']
                if generator=='ngen':
                    preferred=(c['backend']=='streamed' and c['lanes']==4 and c.get('pe')==2
                               and c['radix']==8 and c.get('stage_groups')==1 and c['reduction']=='barrett')
                else:
                    preferred=(c['backend']=='full-throughput' and c['lanes']==2
                               and c['fractional_bits']==32 and c.get('omit_low_diagonals')==1)
                return (not preferred,r['name'])
            heldout.append(min(options,key=key)['name'])
    return calibration,heldout


def choose(rows, observed, target, policy, seed, step):
    ordered=sorted(rows,key=lambda r:r['name'])
    if not ordered: raise ValueError('no candidates remaining')
    if policy=='enumerate': return ordered[0],None
    if policy=='random': return random.Random(f'{seed}:{step}').choice(ordered),None
    if policy!='model': raise ValueError('unknown search policy')
    ranked=[]
    for r in ordered:
        p=predict(r,observed)
        if p['resources'] is None:
            rank=(0,0,0,r['name'])  # Explore an uncalibrated family before trusting it.
        else:
            ceiling=limits(target)
            excess=sum(max(0,p['resources'][k]-ceiling[k])/max(1,ceiling[k]) for k in RESOURCES)
            rank=(1 if excess==0 else 2,excess,-performance(r,target)['modeled_products_per_second'],r['name'])
        ranked.append((rank,r,p))
    _,row,prediction=min(ranked,key=lambda item:item[0])
    return row,prediction


def heldout_errors(rows, calibration, heldout):
    byname={r['name']:r for r in rows}
    observed=[(byname[name],e) for name,e in calibration.items()]
    result=[]
    for name,e in heldout.items():
        p=predict(byname[name],observed)
        item=dict(name=name,prediction=p,measured=e.get('metrics'),passed=e.get('passed',False))
        if p['resources'] is not None and e.get('passed'):
            item['absolute_error']={k:abs(p['resources'][k]-e['metrics'][k]) for k in RESOURCES}
            item['relative_error']={k:abs(p['resources'][k]-e['metrics'][k])/e['metrics'][k]
                                    if e['metrics'][k] else None for k in RESOURCES}
        result.append(item)
    return result
