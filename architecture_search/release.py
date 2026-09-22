"""Fixed covering campaigns and acceptance accounting for the product DSE release."""
from . import products

TARGET={'part':'xcu280-fsvh2892-2L-e','tool_version':'2023.2','clock_period_ns':4.0}


def configurations(n=16, matrix=False):
    w=products.workload(n)
    space={'reductions':['barrett','montgomery','shoup','auto'],'profiles':['baseline','f300'],'guard_bits':[0,2]}
    legal=products.candidates(w,space);selected=[]
    def pick(**terms):
        defaults=({'profile':'baseline','lanes':2,'pe':1,'radix':2,'reduction':'barrett','stage_groups':1}
                  if terms.get('generator')=='ngen' else {'lanes':2,'fractional_bits':32 if n>=64 else 24,'guard_bits':0})
        if terms.get('backend')=='fully-parallel':defaults['lanes']=n;defaults.pop('pe')
        elif terms.get('backend')=='stage-parallel':defaults.pop('pe')
        matches=[c for c in legal if all(c.get(k)==v for k,v in {**defaults,**terms}.items())]
        if len(matches)!=1:raise ValueError(f'covering point has {len(matches)} matches: {terms}')
        if matches[0] not in selected:selected.append(matches[0])
    for backend in ('streamed','stage-parallel','fully-parallel'):pick(generator='ngen',backend=backend)
    pick(generator='ngen',backend='streamed',pe=2)
    for backend in ('full-throughput','compact'):pick(generator='sgen',backend=backend)
    if matrix:
        for backend in ('streamed','stage-parallel'):
            pick(generator='ngen',backend=backend,lanes=4)
            pick(generator='ngen',backend=backend,profile='f300')
        for reduction in ('montgomery','shoup','auto'):
            pick(generator='ngen',backend='streamed',reduction=reduction)
            pick(generator='ngen',backend='stage-parallel',reduction=reduction)
        pick(generator='ngen',backend='streamed',stage_groups=2)
        for radix in (4,8):
            if (n.bit_length()-1)%(radix.bit_length()-1)==0:pick(generator='ngen',backend='streamed',radix=radix)
        for backend in ('full-throughput','compact'):
            pick(generator='sgen',backend=backend,lanes=4)
            for frac in (16,24,32):pick(generator='sgen',backend=backend,fractional_bits=frac)
        pick(generator='sgen',backend='compact',guard_bits=2)
        pick(generator='ngen',backend='fully-parallel',profile='f300')
    return {**space,'configurations':selected}


def campaign(n=16,matrix=False,hardware=False,period=4):
    space=configurations(n,matrix)
    return dict(workload=products.workload(n),space=space,target={**TARGET,'clock_period_ns':period,
                       **({'input_hold_buffer_stages':1} if hardware else {})},
                stages=['simulation','synthesis','route'] if hardware else ['simulation'],
                evaluation={'simulator':'verilator' if n>=64 else 'iverilog','timeout_seconds':3600 if n>=64 else 600},
                budget={'hours':12 if hardware else (2.4 if matrix else 2),
                        'functional':len(space['configurations']),'synthesis':6 if hardware else 0,'route':4 if hardware else 0})


def _routed(record, target):
    from .model import frontier, evidence_integrity
    evidence=record.get('evidence',{}).get('route',{})
    return (evidence.get('timing_clean') is True and evidence_integrity(evidence)=='verified' and
            bool(frontier([record], {'products_per_second':'max','latency_ns':'min',
                                    'lut':'min','ff':'min','dsp':'min','bram':'min','uram':'min'},
                          'route', target)))


def accept(report,campaign):
    records=report.get('candidates',[]); expected=campaign['space']['configurations']
    accounted=(len(records)==len(expected) and
               all(sum(r['configuration']==c for r in records)==1 for c in expected))
    bad=[r['id'] for r in records if r.get('status') not in ('complete','duplicate','numerically_unqualified','hardware_failed','pruned')]
    valid=[r for r in records if r.get('correct') and r.get('declared',{}).get('certificate',{}).get('qualified')]
    families={r['configuration']['backend'] for r in valid}
    required={c['backend'] for c in expected}
    # The evidence-aware frontier has checked target, timing, metrics and artifact integrity.
    routed={r['configuration']['generator'] for r in valid
            if _routed(r, campaign.get('target',{}))}
    ok=accounted and not bad and families>=required
    if 'route' in campaign['stages']:ok=ok and routed=={'ngen','sgen'}
    return dict(passed=ok,accounted=accounted,required_candidates=len(expected),recorded_candidates=len(records),
                missing_families=sorted(required-families),failed_candidates=bad,routed_backends=sorted(routed))
