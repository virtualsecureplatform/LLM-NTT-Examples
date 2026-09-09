"""Application-anchored benchmark definitions, separate from architecture choices."""
from __future__ import annotations
import copy
from . import oracle

AUTONTT='https://zhenman.github.io/files/C45-FCCM2025-AutoNTT.pdf'
PROTEUS='https://eprint.iacr.org/2023/267.pdf'
SEAL='https://github.com/microsoft/SEAL/blob/119dc32e135cb89c1062076a69310d4413ebc824/native/examples/5_ckks_basics.cpp'
TARGET={'part':'xcu280-fsvh2892-2L-e','tool_version':'2023.2','clock_period_ns':4.0,
        'clock_source':'BUFGCE_X0Y0','io_reference_pin':'input_full_reg/C',
        'io_delays_ns':{'input_min':.5,'input_max':1.,'output_min':0.,'output_max':1.},
        'output_hold_buffer_stages':2}

def fixed_field(n,q,psi=None):
    if not oracle.is_prime(q) or (q-1)%(2*n):raise ValueError('full negacyclic NTT requires prime q = 1 mod 2N')
    if psi is None:
        for a in range(2,10000):
            candidate=pow(a,(q-1)//(2*n),q)
            if pow(candidate,n,q)==q-1:psi=candidate;break
        else:raise ValueError('could not find primitive root')
    result={'n':n,'q':str(q),'psi':str(psi),'root':str(psi*psi%q)}
    oracle.validate({**result,'negacyclic':True})
    return result

def definitions(seal_trace):
    if seal_trace.get('correct') is not True or seal_trace.get('seal_revision')!='119dc32e135cb89c1062076a69310d4413ebc824':
        raise ValueError('verified pinned SEAL trace required')
    result=[]
    def add(name,domain,split,source,scope,negacyclic=True):
        result.append({'name':name,'domain':domain,'split':split,'source':source,'scope':scope,'negacyclic':negacyclic})
    for name,n,bits,split in [('fhe4k32',4096,32,'development'),('fhe4k60',4096,60,'development'),('fhe16k54',16384,54,'held-out'),('fhe64k54',65536,54,'held-out')]:
        add(name,oracle.field(n,bits),split,AUTONTT,'Paper size/width; deterministic benchmark prime, not a claim to reproduce the paper exact modulus. Single RNS limb.')
    domains={}
    for sample in seal_trace['samples']:
        w=sample['workload'];oracle.validate(w)
        if w['n']!=8192 or sample.get('correct') is not True:raise ValueError('invalid SEAL sample')
        d={k:w[k] for k in ('n','q','root','psi')}
        if w['q'] in domains and domains[w['q']]!=d:raise ValueError('SEAL root differs between directions')
        domains[w['q']]=d
    if len(domains)!=4 or sorted(int(q).bit_length() for q in domains)!=[40,40,60,60]:raise ValueError('expected four distinct CKKS primes')
    for i,(q,d) in enumerate(sorted(domains.items(),key=lambda item:int(item[0]))):
        add(f'ckks8k-prime{i}',d,'development',SEAL,'Exact prime/root observed in SEAL CKKS example. Index sorts primes numerically; it is not an RNS chain position.')
    for n in (1024,65536):
        add(f'goldilocks{n}',fixed_field(n,(1<<64)-(1<<32)+1),'extension',PROTEUS,'Goldilocks cyclic NTT/INTT; 64K is a proposed scale-up of the field used by HOGE/Proteus examples.',False)
    add('mldsa256',fixed_field(256,8380417,1753),'extension','https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf','ML-DSA field and root; natural-order normalized NTT boundary, not a complete signature implementation.')
    return result

def campaign(case,direction,validation=False):
    w={'kind':'generic',**case['domain'],'direction':direction,'negacyclic':case['negacyclic'],'lanes':4}
    oracle.validate(w)
    return {'workload':w,'target':copy.deepcopy(TARGET),
            'budget':{'hours':12,'functional':64,'synthesis':12,'route':4},
            'stages':['simulation'] if validation else ['simulation','synthesis'],
            'evaluation':{'simulator':'verilator','timeout_seconds':3600},
            'space':{'pe':[2] if validation else [1,2,4,8],'radix':[2] if validation else [2,4],
                     'reductions':['montgomery'] if validation else ['montgomery','barrett','shoup'],
                     'stage_groups':[1] if validation else [1,2,4]},
            'benchmark':{'name':case['name'],'split':case['split'],'source':case['source'],'scope':case['scope'],
                         'ordering':'natural input and output','residues':'canonical [0,q)','inverse_normalization':'multiply by N^-1',
                         'performance_status':'unmeasured','resource_budget_note':'Assign the same explicit caps to all policies in a measured study; these templates do not claim a complete reference frontier.'}}

def polynomial_product_check(domain,negacyclic=True):
    # Sparse operands allow a separate O(N) exact convolution at every size.
    n,q=int(domain['n']),int(domain['q']);a=[(i*17+3)%q for i in range(n)];b=[0]*n
    taps={0:q-1,1:7,n//2:11,n-1:13}
    for i,v in taps.items():b[i]=v
    w={**domain,'negacyclic':negacyclic,'direction':'forward'}
    x,y=oracle.transform(a,w),oracle.transform(b,w)
    actual=oracle.transform([u*v%q for u,v in zip(x,y)],{**w,'direction':'inverse'})
    expected=[]
    for i in range(n):
        total=0
        for j,v in taps.items():
            k=i-j;total+=(-1 if negacyclic and k<0 else 1)*a[k%n]*v
        expected.append(total%q)
    return actual==expected
