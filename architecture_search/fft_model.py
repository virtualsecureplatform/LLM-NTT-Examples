"""Independent integer model of the two supported SGen radix-2 factorizations.

No generator code is imported. Permutations are explicit index rotations;
every real multiplication truncates independently before the complex sum.
"""
from .numerics import signed


def transform(values,meta):
    n=meta['transform_size']; bits=n.bit_length()-1
    width=meta['integer_bits']+meta['fractional_bits']; tf=meta['twiddle_fractional_bits']
    inverse=meta['family'] in ('ICTDFT','IItPeaseFused')
    compact=meta['family'] in ('ItPeaseFused','IItPeaseFused')
    if len(values)!=n:raise ValueError('FFT model input length mismatch')
    mask=(1<<width)-1
    def wrap(x):return signed(x&mask,width)
    def rotate(x,r,b):
        if not b:return 0
        r%=b; mask=(1<<b)-1
        return ((x>>r)|(x<<(b-r)))&mask
    def reverse(x):return int(f'{x:0{bits}b}'[::-1],2)
    def permute(a,fn):
        out=[None]*n
        for i,v in enumerate(a):out[fn(i)]=v
        return out
    tw=[(signed(e['real_bits'],width),signed(e['imag_bits'],width)) for e in meta['twiddles']]
    def multiply(z,p):
        a,b=z;c,d=tw[p%n]
        return wrap(((a*c)>>tf)-((b*d)>>tf)),wrap(((a*d)>>tf)+((b*c)>>tf))
    def butterfly(a):
        out=[]
        for i in range(0,n,2):
            x,y=a[i],a[i+1]
            out.extend(((wrap(x[0]+y[0]),wrap(x[1]+y[1])),(wrap(x[0]-y[0]),wrap(x[1]-y[1]))))
        return out
    a=[tuple(reversed(v)) if inverse else tuple(v) for v in values]
    if compact:
        for layer in range(bits):
            a=permute(a,lambda i:rotate(i,-1,bits))
            a=butterfly(a)
            a=[multiply(z,(i&1)*(((i>>1)>>layer)<<layer)) for i,z in enumerate(a)]
        a=permute(a,reverse)
    else:
        a=permute(a,reverse)
        for layer in reversed(range(bits)):
            def qindex(i):
                low=bits-layer-1
                j=(i>>low)<<low | rotate(i&((1<<low)-1),1,low)
                low+=1
                return (j>>low)<<low | rotate(j&((1<<low)-1),bits-layer-1,low)
            a=permute(a,qindex)
            if layer!=bits-1:
                a=[multiply(z,(i&1)*((i>>1)%(1<<(bits-layer-1)))*(1<<layer)) for i,z in enumerate(a)]
            a=butterfly(a)
        a=permute(a,lambda i:rotate(i,1,bits))
    return [tuple(reversed(v)) if inverse else v for v in a]


def product_intermediates(a,b,forward,inverse):
    n=len(a);frac=forward['fractional_bits'];width=forward['integer_bits']+frac;mask=(1<<width)-1
    def wrap(x):return signed(x&mask,width)
    fa=transform([(v<<frac,0) for v in a]+[(0,0)]*n,forward)
    fb=transform([(v<<frac,0) for v in b]+[(0,0)]*n,forward)
    pointwise=[]
    for (ar,ai),(br,bi) in zip(fa,fb):
        pointwise.append((wrap(((ar*br)>>frac)-((ai*bi)>>frac)),wrap(((ar*bi)>>frac)+((ai*br)>>frac))))
    inv=transform(pointwise,inverse)
    return fa,fb,pointwise,inv
