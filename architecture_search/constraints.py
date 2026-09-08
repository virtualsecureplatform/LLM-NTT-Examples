"""Optimistic throughput bounds, separate from measured implementation evidence."""
import math
from .model import metric_number


def bandwidth_bound(workload, bandwidth):
    if not bandwidth:return None
    if workload.get('kind')!='generic':raise ValueError('bandwidth constraints currently require a generic workload')
    allowed={'input_bits_per_second','output_bits_per_second','shared_bits_per_second','coefficient_bits'}
    if set(bandwidth)-allowed:raise ValueError('unknown bandwidth constraint')
    width=bandwidth.get('coefficient_bits',int(workload['q']).bit_length())
    if not isinstance(width,int) or isinstance(width,bool) or width<int(workload['q']).bit_length():raise ValueError('transport coefficient width must cover the field')
    bounds=[];bits=int(workload['n'])*width
    for key,factor in (('input_bits_per_second',1),('output_bits_per_second',1),('shared_bits_per_second',2)):
        if key in bandwidth:
            rate=bandwidth[key]
            if not metric_number(rate) or rate<=0:raise ValueError('bandwidth must be finite and positive')
            bounds.append({'constraint':key,'bits_per_transform':factor*bits,'upper_transforms_per_second':rate/(factor*bits)})
    if not bounds:raise ValueError('at least one input, output or shared bandwidth limit is required')
    return {'upper_transforms_per_second':min(b['upper_transforms_per_second'] for b in bounds),'terms':bounds,'assumption':'One full input and output vector per transform, no compression or inter-transform reuse. Bandwidth is a declared service limit, not a measured board rate.'}


def analyze(workload, configuration, target, bandwidth=None, requirements=None):
    requirements=requirements or {}
    if set(requirements)-{'min_transforms_per_second'}:raise ValueError('unknown search requirement')
    minimum=requirements.get('min_transforms_per_second')
    if minimum is not None and (not metric_number(minimum) or minimum<=0):raise ValueError('minimum throughput must be finite and positive')
    if (minimum is not None or bandwidth) and workload.get('kind')!='generic':raise ValueError('throughput requirements currently require a generic workload')
    transport=bandwidth_bound(workload,bandwidth or {})
    terms=[]
    if transport:terms+=transport['terms']
    if workload.get('kind')=='generic':
        period=target.get('clock_period_ns',4.0)
        if not metric_number(period) or period<=0:raise ValueError('clock period must be finite and positive')
        n=int(workload['n']);lanes=configuration.get('lanes',workload.get('lanes',1));frequency=1e9/period
        terms.append({'constraint':'registered_stream_ports','minimum_cycles_per_transform':n//lanes,'upper_transforms_per_second':frequency/(n//lanes)})
        if configuration.get('backend')=='streamed' and configuration.get('radix')==2:
            # At least one group contains ceil(log2(N)/groups) stages. Each
            # stage must issue N/2 butterflies through PE II=1 arithmetic units.
            stages=(n.bit_length()-1+configuration['stage_groups']-1)//configuration['stage_groups']
            cycles=math.ceil((n//2)*stages/configuration['pe'])
            terms.append({'constraint':'radix2_butterfly_issue_capacity','minimum_cycles_per_transform':cycles,'upper_transforms_per_second':frequency/cycles})
    upper=min((t['upper_transforms_per_second'] for t in terms),default=None)
    return {'schema':'ntt-optimistic-throughput-bound-v1','upper_transforms_per_second':upper,'required_transforms_per_second':minimum,
            'pruned':minimum is not None and upper is not None and upper<minimum,'terms':terms,
            'limitation':'Optimistic necessary condition only. Omits pipeline drain, memory stalls, twists, and timing closure; passing this bound does not prove feasibility.'}
