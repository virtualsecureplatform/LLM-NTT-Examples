"""Version-2 exact polynomial contracts and independent reconstruction arithmetic."""
import itertools
import math
import random
from .oracle import is_prime

PRIMES=(65537,469762049,1811939329,2013265921)


def workload(n=16,bound=7,ring='negacyclic',modulus=None):
    return dict(kind='polynomial_product',version=2,n=n,ring=ring,
                a_range=[-bound,bound],b_range=[-bound,bound],modulus=modulus,
                correctness='certified-exact',operands='fresh',lanes=2)


def tfhe_workload():
    return {**workload(1024,modulus=1<<32),'a_range':[0,(1<<32)-1],'b_range':[0,(1<<32)-1]}


def validate(w):
    if set(w)!=set(workload()) or w['kind']!='polynomial_product' or type(w['version']) is not int or w['version']!=2:
        raise ValueError('invalid version-2 product contract')
    if type(w['n']) is not int or w['n']<8 or w['n']>1024 or w['n']&(w['n']-1):
        raise ValueError('version-2 size must be a power of two in 8..1024')
    if w['ring'] not in ('linear','cyclic','negacyclic'):raise ValueError('unsupported polynomial ring')
    for key in ('a_range','b_range'):
        interval=w[key]
        if not isinstance(interval,list) or len(interval)!=2 or any(type(x) is not int for x in interval):
            raise ValueError('operand bounds must be two integers')
        if not -(1<<31)<=interval[0]<=interval[1]<(1<<32) or (interval[0]<0 and interval[1]>=(1<<31)):
            raise ValueError('operand interval exceeds a 32-bit encoding')
    if w['modulus'] is not None and (type(w['modulus']) is not int or not 2<=w['modulus']<=1<<32):
        raise ValueError('output modulus must be in 2..2^32')
    if w['correctness']!='certified-exact' or w['operands']!='fresh' or type(w['lanes']) is not int or w['lanes']!=2:
        raise ValueError('version-2 products require fresh exact two-lane transactions')


def magnitude(w,key):return max(abs(v) for v in w[key+'_range'])
def bound(w):return w['n']*magnitude(w,'a')*magnitude(w,'b')
def output_count(w):return 2*w['n']-1 if w['ring']=='linear' else w['n']
def output_width(w):return (w['modulus']-1).bit_length() if w['modulus'] else bound(w).bit_length()+1


def input_width(w,key):
    lo,hi=w[key+'_range']
    return max(1,hi.bit_length()) if lo>=0 else max(1,(~lo).bit_length(),hi.bit_length())+1


def roots(q,length,negacyclic):
    order=length*(2 if negacyclic else 1)
    if not is_prime(q) or (q-1)%order:raise ValueError('incompatible NTT prime')
    generator=2
    while True:
        root=pow(generator,(q-1)//order,q)
        if pow(root,order//2,q)==q-1:break
        generator+=1
    return dict(q=q,root=pow(root,2,q) if negacyclic else root,psi=root if negacyclic else None)


def basis(w):
    validate(w);length=2*w['n'] if w['ring']=='linear' else w['n'];negative=w['ring']=='negacyclic'
    compatible=[q for q in PRIMES if (q-1)%(length*(2 if negative else 1))==0]
    for count in range(1,len(compatible)+1):
        options=[qs for qs in itertools.combinations(compatible,count) if math.prod(qs)>2*bound(w)]
        if options:return [roots(q,length,negative) for q in min(options,key=math.prod)]
    raise ValueError('prime catalog cannot certify integer reconstruction')


def schoolbook(w,a,b):
    validate(w)
    if len(a)!=w['n'] or len(b)!=w['n']:raise ValueError('operand length mismatch')
    for key,values in (('a',a),('b',b)):
        lo,hi=w[key+'_range']
        if any(type(v) is not int or not lo<=v<=hi for v in values):raise ValueError('operand outside declared range')
    n=w['n'];out=[0]*output_count(w)
    for i,x in enumerate(a):
        for j,y in enumerate(b):
            k=i+j
            if w['ring']=='linear':out[k]+=x*y
            else:out[k%n]+=(-1 if w['ring']=='negacyclic' and k>=n else 1)*x*y
    return [x%w['modulus'] for x in out] if w['modulus'] else out


def vectors(w,random_count=64,seed=1):
    validate(w);rng=random.Random(seed);n=w['n']
    def special(key):
        lo,hi=w[key+'_range'];zero=min(hi,max(lo,0))
        return [[zero]*n,[lo]*n,[hi]*n,[lo if i%2 else hi for i in range(n)],
                [hi]+[zero]*(n-1),[zero]*(n-1)+[lo]]
    pairs=list(itertools.product(special('a'),special('b')))
    pairs.extend(([rng.randint(*w['a_range']) for _ in range(n)],
                  [rng.randint(*w['b_range']) for _ in range(n)]) for _ in range(random_count))
    return pairs


def reconstruct(residues,primes):
    q=math.prod(primes)
    value=sum(r*(q//p)*pow(q//p,-1,p) for r,p in zip(residues,primes))%q
    return value-q if value>q//2 else value


def digit(value,index,bits,signed):
    width=min(4,bits-4*index)
    result=(value>>(4*index))&((1<<width)-1)
    if signed and 4*index+width==bits and result&(1<<(width-1)):result-=1<<width
    return result


def candidates(w,space=None):
    validate(w);space=space or {}
    axes={'generators':['ngen','sgen'],'ngen_backends':['streamed'],'sgen_backends':['compact'],
          'lanes':[2],'pe':[1],'radix':[2],'stage_groups':[1],'reductions':['barrett'],
          'profiles':['baseline'],'fractional_bits':[32,48],'guard_bits':[0]}
    legal={'generators':['ngen','sgen'],'ngen_backends':['streamed','stage-parallel','fully-parallel'],
           'sgen_backends':['compact','full-throughput'],'lanes':[2,4],'pe':[1,2],
           'radix':[2,4,8],'stage_groups':[1,2],'reductions':['barrett','montgomery','shoup','auto'],
           'profiles':['baseline','f300','split-barrett'],'fractional_bits':[24,32,40,48],'guard_bits':[0,2]}
    if set(space)-set(axes)-{'configurations'}:raise ValueError('unknown version-2 search axis')
    for key in axes:
        if key in space:
            values=space[key]
            if not isinstance(values,list) or not values or any(type(v) is not type(legal[key][0]) or v not in legal[key] for v in values):
                raise ValueError('invalid version-2 axis: '+key)
            axes[key]=values
    result=[];length=2*w['n'] if w['ring']=='linear' else w['n']
    if 'ngen' in axes['generators']:
        basis(w)
        for backend,lanes,pe,radix,groups,reduction,profile in itertools.product(
                axes['ngen_backends'],axes['lanes'],axes['pe'],axes['radix'],axes['stage_groups'],axes['reductions'],axes['profiles']):
            if (length.bit_length()-1)%(radix.bit_length()-1) or (groups>1 and radix!=2):continue
            if profile=='split-barrett' and backend!='fully-parallel':continue
            if backend!='streamed' and (pe!=1 or radix!=2 or groups!=1):continue
            if backend=='fully-parallel' and (reduction!='barrett' or w['n']>256):continue
            c=dict(generator='ngen',backend=backend,lanes=length if backend=='fully-parallel' else lanes,
                   radix=radix,stage_groups=groups,reduction=reduction,profile=profile,arithmetic='rns')
            if backend=='streamed':c['pe']=pe
            if c not in result:result.append(c)
    if 'sgen' in axes['generators']:
        split=max(magnitude(w,'a'),magnitude(w,'b'))>15
        magnitude_bound=15 if split else max(magnitude(w,'a'),magnitude(w,'b'))
        for backend,lanes,frac,guard in itertools.product(axes['sgen_backends'],axes['lanes'],axes['fractional_bits'],axes['guard_bits']):
            if w['n']>256 and backend!='compact':continue
            result.append(dict(generator='sgen',backend=backend,lanes=lanes,radix=2,
                               fractional_bits=frac,guard_bits=guard,
                               integer_bits=(4*(2*w['n'])**3*magnitude_bound**2).bit_length()+1+guard,
                               arithmetic='split-radix16' if split else 'direct'))
    if 'configurations' in space:
        selected=space['configurations']
        if not isinstance(selected,list) or not selected or any(c not in result for c in selected):
            raise ValueError('selected version-2 configuration is illegal')
        result=selected
    return result
