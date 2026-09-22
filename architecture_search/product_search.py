"""Product-only advisory acquisition. Predictions never establish feasibility."""
import math
import random
from .model import digest,metric_number


def features(workload, record):
    c=record['configuration'];n=workload['n'];fft=c['generator']=='sgen'
    length=2*n if fft or workload.get('ring')=='linear' else n;bits=length.bit_length()-1
    width=c.get('integer_bits',17)+c.get('fractional_bits',0) if fft else 17
    prime_count=1;digit_products=1
    if workload.get('version')==2:
        from . import wide_products as wide
        if not fft:
            fields=wide.basis(workload);prime_count=len(fields);width=max(f['q'].bit_length() for f in fields)
        elif c.get('arithmetic')=='split-radix16':
            da=(wide.input_width(workload,'a')+3)//4;db=(wide.input_width(workload,'b')+3)//4
            digit_products=sum(not(workload['modulus']==1<<32 and i+j>=8) for i in range(da) for j in range(db))
    lanes=c['lanes'];pe=c.get('pe',1);groups=c.get('stage_groups',1)
    replication=(length//2*bits if c['backend']=='fully-parallel' else
                 lanes//2*bits if c['backend'] in ('stage-parallel','full-throughput') else pe*lanes//2)
    declaration=record.get('declared',{})
    metadata=declaration.get('cores',[declaration.get('forward',{}),declaration.get('inverse',{})])
    real_multiplies=0;register_bits=0;memory_bits=0
    for copies,meta in zip((2,1),metadata):
        for node in meta.get('operation_contract',{}).get('nodes',[]):
            if node['op']=='Times':real_multiplies+=copies
            elif node['op']=='Register':register_bits+=copies*node['width']*node['cycles']
            elif node['op']=='RAM':
                nodes=meta['operation_contract']['nodes'];address=nodes[node['inputs'][1]]['width']
                memory_bits+=copies*node['width']*(1<<address)
    if not real_multiplies:real_multiplies=3*replication*(4 if fft else prime_count)
    # Frame-adapter storage is charged even when core operation metadata exists.
    memory_bits+=3*length*width*(2 if fft else prime_count)*4
    interval=record.get('evaluation',{}).get('metrics',{}).get('initiation_interval_cycles')
    if interval is None:
        interval=max(n//2,(length//lanes)*(bits if c['backend'] in ('compact','streamed') else 1))*digit_products
    return dict(n=n,length=length,width=width,lanes=lanes,pe=pe,stage_groups=groups,
                multiplies=real_multiplies+2*(4 if fft else 1),register_bits=register_bits,
                memory_bits=memory_bits,interval=interval,prime_count=prime_count,digit_products=digit_products)


def estimate(workload, candidate, observed=(), learned=False):
    f=features(workload,candidate);c=candidate['configuration']
    # Explicit uncalibrated arithmetic/storage proxy, not a device resource bound.
    lut=f['multiplies']*f['width']**2/4+f['register_bits']/8+f['memory_bits']/32
    result=dict(lut=lut,interval=f['interval'],method='analytical-proxy',samples=0,features=f)
    if not learned:return result
    samples=[]
    for r in observed:
        e=r.get('evidence',{}).get('synthesis',{});m=e.get('metrics',{})
        if r['configuration']['generator']!=c['generator'] or not e.get('implementation_passed'):continue
        if not metric_number(m.get('lut')) or m['lut']<0:continue
        other=features(workload,r)
        distance=sum(abs(math.log2(1+f[k])-math.log2(1+other[k])) for k in f if k!='interval')
        distance+=sum(c.get(k)!=r['configuration'].get(k) for k in ('backend','radix','reduction','profile'))
        samples.append((distance,digest(r['configuration']),float(m['lut'])))
    if not samples:return result
    neighbors=sorted(samples)[:3];weights=[1/(0.25+d) for d,_,_ in neighbors]
    values=[v for _,_,v in neighbors]
    result.update(lut=sum(w*v for w,v in zip(weights,values))/sum(weights),method='product-nearest',
                  samples=len(samples),neighbor_range=[min(values),max(values)],
                  limitation='Neighbor range is a heuristic, not a confidence interval.')
    return result


def choose(workload, remaining, observed, policy, seed, step):
    if policy not in ('enumerate','random','analytical','cost'):raise ValueError('unsupported product policy')
    ordered=sorted(remaining,key=lambda r:digest(r['configuration']))
    if not ordered:raise ValueError('empty acquisition pool')
    rng=random.Random(f'{seed}:{step}')
    if policy=='enumerate':return ordered[0],None
    if policy=='random' or step%4==3:return rng.choice(ordered),dict(method='seeded-exploration')
    ranked=[(r,estimate(workload,r,observed,policy=='cost')) for r in ordered]
    frontier=[(r,p) for r,p in ranked if not any(
        q['lut']<=p['lut'] and q['interval']<=p['interval'] and
        (q['lut']<p['lut'] or q['interval']<p['interval']) for _,q in ranked)]
    preference=('lut','interval') if step%2==0 else ('interval','lut')
    return min(frontier,key=lambda pair:(pair[1][preference[0]],pair[1][preference[1]],digest(pair[0]['configuration'])))
