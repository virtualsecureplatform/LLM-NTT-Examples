"""AutoNTT field capture and strict gates for a matched transform comparison."""
import copy
import re
from . import oracle
from pathlib import Path
from .model import evidence_integrity,artifact_manifest
PIN='de1db3fa39d88350c0b69d19f30b1fdcaef6a002'
BOUNDARY=dict(name='preloaded-compute',input_order='natural',output_order='natural',residues='canonical',
              inverse_normalization='N^-1',includes=['operand-storage','twiddle-storage','permutation','control','adapters'],
              excludes=['initialization','host-transfers','off-chip-transfers'])


def instrument_host(source):
    marker='  printf("\\nRun completed\\n");'
    if source.count(marker)!=1:raise ValueError('unrecognized pinned AutoNTT host completion marker')
    trace=r'''
  for(unsigned limb=0;limb<PARA_LIMBS;++limb){
    std::cout << "LLMNTT field " << N << " " << workingModulus_arr[limb].to_uint64()
      << " " << root_arr[limb].to_uint64() << " " << limb << "\n";
    std::cout << "LLMNTT input";for(auto v:invec[limb])std::cout << " " << v.to_uint64();std::cout << "\n";
    std::cout << "LLMNTT forward";for(auto v:kernelOutArr[limb])std::cout << " " << v.to_uint64();std::cout << "\n";
    std::cout << "LLMNTT inverse";for(auto v:inv_kernelOutArr[limb])std::cout << " " << v.to_uint64();std::cout << "\n";
  }
'''
    return source.replace(marker,trace+marker)


def verify_trace(text,architecture):
    if architecture not in ('I','D','H'):raise ValueError('unknown AutoNTT architecture')
    rows=[line.split()[1:] for line in text.splitlines() if line.startswith('LLMNTT ')]
    if not rows or len(rows)%4:raise ValueError('incomplete AutoNTT kernel trace')
    verified=[]
    for offset in range(0,len(rows),4):
        field,left,forward,inverse=rows[offset:offset+4]
        if field[0]!='field' or left[0]!='input' or forward[0]!='forward' or inverse[0]!='inverse':raise ValueError('bad trace order')
        n,q,root,limb=map(int,field[1:]);w=dict(n=n,q=str(q),root=str(root),negacyclic=False)
        oracle.validate(w);a=list(map(int,left[1:]));f=list(map(int,forward[1:]));inv=list(map(int,inverse[1:]))
        if any(len(x)!=n or any(v<0 or v>=q for v in x) for x in (a,f,inv)):raise ValueError('noncanonical or incomplete trace')
        # Pinned iterative host returns bit-reversed forward output; D/H host
        # rearrangement returns natural order. All three host inverse outputs are natural.
        if architecture=='I':f=[f[int(f'{i:0{n.bit_length()-1}b}'[::-1],2)] for i in range(n)]
        if f!=oracle.transform(a,w) or inv!=oracle.transform(f,{**w,'direction':'inverse'}):
            raise ValueError('independent transform check failed')
        verified.append(dict(field=w,limb=limb,checked_coefficients=2*n))
    return dict(schema='autontt-field-trace-v1',passed=True,architecture=architecture,autontt_revision=PIN,limbs=verified,
                scope='Functional C-simulation trace; not a preloaded compute timing measurement.')


def matched_campaign(trace,direction):
    if trace.get('passed') is not True or trace.get('autontt_revision')!=PIN or len(trace['limbs'])!=1:
        raise ValueError('verified single-limb pinned AutoNTT trace required')
    artifacts=trace.get('artifacts',{})
    if not artifacts or artifact_manifest(artifacts['files'],artifacts['directories'])!=artifacts:
        raise ValueError('trace artifacts missing or changed')
    logs=[Path(p) for p in artifacts['files'] if Path(p).name=='trace.log']
    if len(logs)!=1 or verify_trace(logs[0].read_text(),trace['architecture'])!={k:v for k,v in trace.items() if k!='artifacts'}:
        raise ValueError('field capture does not match kernel trace')
    w=trace['limbs'][0]['field'];n,q=w['n'],int(w['q'])
    if not ((n==1024 and q==(1<<64)-(1<<32)+1) or (n==16384 and q.bit_length()==54)):
        raise ValueError('field outside the bounded AutoNTT study')
    if direction not in ('forward','inverse'):raise ValueError('unknown direction')
    return dict(workload=dict(kind='generic',**w,direction=direction,lanes=4),
        target=dict(part='xcu280-fsvh2892-2L-e',tool_version='2023.2',clock_period_ns=4,input_hold_buffer_stages=1),
        space=dict(backends=['streamed','stage-parallel'],pe=[1,2,4],radix=[2],stage_groups=[1,2],reductions=['barrett'],profiles=['baseline']),
        stages=['simulation','synthesis'],evaluation=dict(simulator='verilator',timeout_seconds=3600),
        budget=dict(hours=24,functional=64,synthesis=8,route=0),
        benchmark=dict(source='AutoNTT runtime field capture',architecture=trace['architecture'],
                       comparison_status='requires measured preloaded-compute adapter; ordinary streaming results are separate'))


def compare(left,right):
    """Reject approximate BU assumptions, boundary mismatch and unsealed metrics."""
    for r in (left,right):
        if r.get('correct') is not True or r.get('boundary')!=BOUNDARY:raise ValueError('unverified or unmatched compute boundary')
        if r.get('initialization_measured_separately') is not True:raise ValueError('initialization accounting missing')
        if r.get('generator')=='autontt' and (r.get('revision')!=PIN or r.get('bu_source')!='measured'):
            raise ValueError('pinned AutoNTT measured BU evidence required')
        for stage in (('functional','route','bu') if r.get('generator')=='autontt' else ('functional','route')):
            e=r.get('evidence',{}).get(stage,{})
            if evidence_integrity(e)!='verified' or e.get('passed') is not True or not e['integrity']['outputs']['files']:
                raise ValueError('unsealed or incomplete comparison evidence')
        if not r['evidence']['route'].get('timing_clean'):raise ValueError('routed timing failed')
    if left['workload']!=right['workload'] or left['evidence']['route']['target']!=right['evidence']['route']['target']:
        raise ValueError('field, direction or target differs')
    return dict(schema='matched-transform-comparison-v1',boundary=copy.deepcopy(BOUNDARY),workload=left['workload'],
                measurements=[{k:r[k] for k in ('generator','architecture','evidence')} for r in (left,right)],
                scope='Measured compute boundary only; excludes off-chip and polynomial-product comparisons.')
