"""Independent conservative arithmetic certificate for the bounded radix-2 FFT path.

Bounds are on complex Euclidean magnitude/error; L1 bounds avoid square roots.
Rational Taylor enclosures include pi uncertainty and a derivative remainder.
This is an arithmetic-model certificate, not a formal RTL equivalence proof.
"""
from fractions import Fraction as Q
from functools import lru_cache
import math
from .model import digest, file_hash
from .products import validate


def upward(x, bits=80):
    scale=1<<bits
    return Q(-(-(x.numerator*scale)//x.denominator),scale)


@lru_cache(None)
def pi_interval():
    def atan(d):
        total=sum((Q((-1)**j,(2*j+1)*d**(2*j+1)) for j in range(80)),Q(0))
        error=Q(1,161*d**161)
        return total-error,total+error
    a,b=atan(5); c,d=atan(239)
    return 16*a-4*d,16*b-4*c


@lru_cache(None)
def trig_interval(size,exponent):
    exponent%=size
    if (4*exponent)%size==0:
        v=((1,0),(0,-1),(-1,0),(0,1))[(4*exponent//size)%4]
        return tuple((Q(x),Q(x)) for x in v)
    if exponent>size//2:exponent-=size
    lo,hi=pi_interval(); pi=(lo+hi)/2
    # Quantize the expansion center; include this displacement in the interval.
    exact=-2*pi*exponent/size; x=Q(int(exact*(1<<100)),1<<100)
    dx=abs(exact-x)+abs(Q(exponent,size))*(hi-lo)
    def series(sine):
        offset=1 if sine else 0
        total=sum(((-1)**j*x**(2*j+offset)/math.factorial(2*j+offset) for j in range(40)),Q(0))
        degree=79 if sine else 78
        error=abs(x)**(degree+1)/math.factorial(degree+1)+dx
        # Outward quantization keeps later propagation rational and inexpensive.
        return -upward(-(total-error)),upward(total+error)
    return series(False),series(True)


def signed(bits,width):
    value=int(bits)
    if not 0<=value<1<<width:raise ValueError('constant does not fit declared width')
    return value-(1<<width) if value&(1<<(width-1)) else value


def twiddle_error(meta):
    size=meta['transform_size']; width=meta['integer_bits']+meta['fractional_bits']; frac=width-2
    if meta['twiddle_integer_bits']!=2 or meta['twiddle_fractional_bits']!=frac:
        raise ValueError('unsupported twiddle format')
    entries=meta['twiddles']
    if len(entries)!=size or [e['exponent'] for e in entries]!=list(range(size)):
        raise ValueError('incomplete twiddle table')
    error=Q(0)
    for i,e in enumerate(entries):
        bounds=trig_interval(size,i); delta=Q(0)
        for key,(lo,hi) in zip(('real_bits','imag_bits'),bounds):
            actual=Q(signed(e[key],width),1<<frac)
            delta+=max(abs(actual-lo),abs(actual-hi))
        error=max(error,delta)
    return upward(error)


def certify(w, forward, inverse, paths=None):
    validate(w); length=2*w['n']; reasons=[]
    required={'schema':'sgen-search-v1','numeric_model':'sgen-radix2-v1','radix':2,'scaling':'1',
              'ram_control':'Dual','complex_packing':'imag-high-real-low',
              'multiply_rounding':'signed-floor-after-each-real-product','addition':'fixed-width-wrap'}
    for m in (forward,inverse):
        if any(m.get(k)!=v for k,v in required.items()) or m.get('transform_size')!=length:
            raise ValueError('unsupported numerical descriptor')
    if (forward['family'],inverse['family']) not in [('CTDFT','ICTDFT'),('ItPeaseFused','IItPeaseFused')]:
        raise ValueError('mismatched FFT families')
    if any(forward[k]!=inverse[k] for k in ('integer_bits','fractional_bits','streaming_width')):
        raise ValueError('mixed FFT formats are not certified')
    if paths:
        for m,p in zip((forward,inverse),paths):
            if file_hash(p)!=m['rtl_sha256']:raise ValueError('FFT artifact hash differs from metadata')
    integer=forward['integer_bits']; frac=forward['fractional_bits']
    if type(integer) is not int or type(frac) is not int or integer<2 or not 1<=frac<=64:
        raise ValueError('invalid fixed-point format')
    eps=Q(1,1<<frac); limit=Q(1<<(integer-1))-eps; maximum=Q(0)
    deltas=[twiddle_error(m) for m in (forward,inverse)]
    def check_range(value):
        nonlocal maximum
        maximum=max(maximum,upward(value))
    def transform(magnitude,error,delta):
        # Both supported decompositions have log2(L) radix-2 layers and at most
        # one complex twiddle multiply per sample per layer. Uniform scale=1
        # introduces no rounding. The compact loop's final pass is a permutation.
        for _ in range(length.bit_length()-1):
            check_range(2*(magnitude+error)*(1+delta)+4*eps)
            error=upward(2*((1+delta)*error+delta*magnitude+4*eps))
            magnitude*=2
            check_range(magnitude+error)
        return magnitude,error
    mf,ef=transform(Q(w['coefficient_bound']),Q(0),deltas[0])
    check_range(2*(mf+ef)**2+4*eps)
    mp=mf*mf; ep=upward(2*mf*ef+ef*ef+4*eps)
    mi,ei=transform(mp,ep,deltas[1])
    final=upward(2*ei/length)  # Widened subtraction and exact power-of-two division.
    if maximum>limit:reasons.append('intermediate overflow cannot be excluded')
    if final>=Q(1,2):reasons.append('final absolute error is not strictly below 1/2')
    def rational(x):return {'numerator':str(x.numerator),'denominator':str(x.denominator)}
    body=dict(schema='fft-arithmetic-certificate-v1',qualified=not reasons,reasons=reasons,
              workload_sha256=digest(w),descriptors_sha256=digest([forward,inverse]),
              rtl_sha256=[forward['rtl_sha256'],inverse['rtl_sha256']],
              final_error_bound=rational(final),maximum_intermediate_bound=rational(maximum),
              representable_maximum=rational(limit),twiddle_error_bounds=list(map(rational,deltas)),
              qualification='conservative-arithmetic-bound-plus-rtl-tests',rounding='nearest-ties-even',
              limitation='Arithmetic-model certificate; hardware equivalence requires the independent RTL checks.')
    return {**body,'certificate_sha256':digest(body)}


def certificate_valid(certificate,w,metas,paths):
    try:return certificate==certify(w,*metas,paths)
    except (ValueError,KeyError,TypeError,OSError):return False
