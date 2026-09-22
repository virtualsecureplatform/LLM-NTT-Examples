"""Versioned exact product workloads and legal, bounded generator configurations."""
from __future__ import annotations
import itertools
import random
from .oracle import is_prime


def workload(n=16):
    return dict(kind='polynomial_product', version=1, n=n, ring='negacyclic',
                coefficient_bound=7, lanes=2, correctness='certified-exact', operands='fresh')


def validate(w):
    if set(w) != set(workload()):
        raise ValueError('product workload requires exactly '+', '.join(workload()))
    if w['kind']!='polynomial_product' or type(w['version']) is not int or w['version']!=1:
        raise ValueError('unsupported product workload version')
    if type(w['n']) is not int or w['n'] not in (8,16,32,64,256):
        raise ValueError('release product sizes are 8,16,32,64,256')
    if w['ring']!='negacyclic' or type(w['coefficient_bound']) is not int or w['coefficient_bound']!=7:
        raise ValueError('release products require negacyclic signed coefficients in [-7,7]')
    if type(w['lanes']) is not int or w['lanes']!=2 or w['correctness']!='certified-exact' or w['operands']!='fresh':
        raise ValueError('products require two lanes, fresh operands and certified-exact outputs')


def output_width(w):
    return (w['n'] * w['coefficient_bound']**2).bit_length()+1


def field(w):
    validate(w)
    n=w['n']; q=65537; psi=pow(3,(q-1)//(2*n),q)
    if not is_prime(q) or q<=2*n*w['coefficient_bound']**2 or pow(psi,n,q)!=q-1:
        raise ValueError('insufficient field or invalid twist')
    return dict(q=q, root=psi*psi%q, psi=psi)


def integer_bits(w, guard=0):
    # Fourfold headroom over an unnormalized length-L inverse of two FFTs.
    return (4*(2*w['n'])**3*w['coefficient_bound']**2).bit_length()+1+guard


def candidates(w, space=None):
    validate(w); space=space or {}; n=w['n']; result=[]
    allowed={'generators','ngen_backends','lanes','pe','radix','stage_groups','reductions','profiles',
             'sgen_backends','fractional_bits','guard_bits','configurations'}
    if set(space)-allowed:raise ValueError('unknown product search axis')
    axes={
        'generators':(['ngen','sgen'],['ngen','sgen']),
        'ngen_backends':(['streamed','stage-parallel','fully-parallel'],['streamed','stage-parallel','fully-parallel']),
        'lanes':([2,4],[2,4]),'pe':([1,2],[1,2]),'radix':([2,4,8],[2,4,8]),
        'stage_groups':([1,2],[1,2]),'reductions':(['barrett'],['barrett','montgomery','shoup','auto']),
        'profiles':(['baseline'],['baseline','f300']),
        'sgen_backends':(['full-throughput','compact'],['full-throughput','compact']),
        'fractional_bits':([16,24,32],[16,24,32]),'guard_bits':([0],[0,2])}
    values={}
    for key,(default,legal) in axes.items():
        values[key]=space.get(key,default)
        if not isinstance(values[key],list) or not values[key] or any(type(x) is not type(legal[0]) or x not in legal for x in values[key]):
            raise ValueError('invalid product search axis: '+key)
    if 'ngen' in values['generators']:
        for backend,profile in itertools.product(values['ngen_backends'],values['profiles']):
            if backend=='fully-parallel':
                result.append(dict(generator='ngen',backend=backend,profile=profile,lanes=n,radix=2,reduction='barrett',stage_groups=1))
            elif backend=='stage-parallel':
                for lanes,reduction in itertools.product(values['lanes'],values['reductions']):
                    result.append(dict(generator='ngen',backend=backend,profile=profile,lanes=lanes,radix=2,reduction=reduction,stage_groups=1))
            else:
                for lanes,pe,radix,groups,reduction in itertools.product(values['lanes'],values['pe'],values['radix'],values['stage_groups'],values['reductions']):
                    if (n.bit_length()-1)%(radix.bit_length()-1) or (groups>1 and radix!=2) or pe>n//radix:continue
                    result.append(dict(generator='ngen',backend=backend,profile=profile,lanes=lanes,pe=pe,radix=radix,reduction=reduction,stage_groups=groups))
    if 'sgen' in values['generators']:
        for backend,lanes,frac,guard in itertools.product(values['sgen_backends'],values['lanes'],values['fractional_bits'],values['guard_bits']):
            result.append(dict(generator='sgen',backend=backend,lanes=lanes,radix=2,fractional_bits=frac,integer_bits=integer_bits(w,guard),guard_bits=guard))
    if 'configurations' in space:
        selected=space['configurations']
        if not isinstance(selected,list) or not selected or any(c not in result for c in selected):
            raise ValueError('selected product configuration outside legal space')
        result=selected
    return [dict(t) for t in {tuple(sorted(c.items())):c for c in result}.values()]


def schoolbook(a,b):
    if len(a)!=len(b):raise ValueError('operand lengths differ')
    n=len(a); out=[0]*n
    for i,x in enumerate(a):
        for j,y in enumerate(b):out[(i+j)%n]+=(1 if i+j<n else -1)*x*y
    return out


def vectors(w, random_count=256, seed=1):
    validate(w); n=w['n']; b=w['coefficient_bound']; rng=random.Random(seed)
    special=[[0]*n,[1]+[0]*(n-1),[0]*(n-1)+[b],[b]*n,[-b]*n,
             [b if i%2 else -b for i in range(n)],[1 if i%3==0 else 0 for i in range(n)]]
    pairs=[(a,c) for a in special for c in special]
    pairs.extend(([rng.randint(-b,b) for _ in range(n)],[rng.randint(-b,b) for _ in range(n)]) for _ in range(random_count))
    return pairs
