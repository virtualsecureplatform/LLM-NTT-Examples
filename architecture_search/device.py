"""FPGA budgets and complete-product bandwidth estimates; predictions are advisory."""
import json
import math
from pathlib import Path
from . import wide_products as wide
from .model import metric_number

RESOURCES = ('lut', 'ff', 'dsp', 'bram36', 'uram')


def load_target(path):
    target = json.loads(Path(path).read_text())
    if target.get('schema') != 'polynomial-device-v1':
        raise ValueError('expected polynomial-device-v1')
    if target.get('implementation_context','standalone') not in ('standalone','registered-harness-v1','registered-harness-v2'):
        raise ValueError('unknown implementation context')
    if target['implementation_directive'] not in ('Default','ExploreHoldFix','HoldFix'):
        raise ValueError('unsupported implementation directive')
    for key in ('clock_mhz', 'bandwidth_bytes_per_second', 'resource_fraction'):
        if not metric_number(target.get(key)) or target[key] <= 0:
            raise ValueError('invalid target ' + key)
    if target['resource_fraction'] > 1:
        raise ValueError('resource_fraction must be <= 1')
    if not 0 <= target.get('io_delay_fraction', -1) < .5:
        raise ValueError('io_delay_fraction must be in [0, 0.5)')
    if not target.get('part') or not target.get('vivado_version'):
        raise ValueError('part and Vivado version are required')
    if target.get('implementation_seed') != 'tool-default':
        raise ValueError('this backend supports the Vivado default seed only')
    for key in RESOURCES:
        if not metric_number(target['capacity'].get(key)) or target['capacity'][key] < 0:
            raise ValueError('invalid capacity ' + key)
    if set(target.get('resource_limits', {})) - set(RESOURCES):
        raise ValueError('unknown resource limit')
    for key, value in target.get('resource_limits', {}).items():
        if not metric_number(value) or not 0 <= value <= target['capacity'][key]:
            raise ValueError('invalid resource limit ' + key)
    return target


def limits(target):
    return {k: target.get('resource_limits', {}).get(k, math.floor(target['capacity'][k] * target['resource_fraction']))
            for k in RESOURCES}


def resources_fit(metrics, target):
    return all(metric_number(metrics.get(k)) and 0 <= metrics[k] <= v for k, v in limits(target).items())


def performance(row, target):
    w = row['workload']
    if not row.get('passed') or any(not metric_number(row.get(k)) or row[k] <= 0
                                  for k in ('latency_cycles', 'initiation_interval_cycles')):
        raise ValueError('qualified positive product timing is required')
    # Byte-aligned coefficients; inputs and output share the aggregate BW budget.
    traffic = w['n'] * sum((wide.input_width(w,k) + 7)//8 for k in ('a','b'))
    traffic += wide.output_count(w) * ((wide.output_width(w) + 7)//8)
    hz = target['clock_mhz'] * 1e6
    compute = hz / row['initiation_interval_cycles']
    memory = target['bandwidth_bytes_per_second'] / traffic
    return dict(bytes_per_product=traffic, kernel_products_per_second=compute,
                bandwidth_products_per_second=memory, modeled_products_per_second=min(compute,memory),
                kernel_latency_seconds=row['latency_cycles']/hz,
                modeled_cold_latency_seconds=row['latency_cycles']/hz + traffic/target['bandwidth_bytes_per_second'],
                transfer_model='aggregate byte-aligned traffic; resident twiddles/intermediates; steady-state ceiling, not board measurement')


def feasible(row, routed, target, error_limit):
    from .model import evidence_integrity
    m = routed.get('metrics', {})
    harness_ok = (target.get('implementation_context','standalone') == 'standalone' or
                  (routed.get('harness_verified') is True and routed.get('harness_sha256') and
                   all(k in routed.get('integrity',{}).get('measurement',{}) for k in ('harness_verified','harness_sha256','harness_validation','scope'))
                   and routed.get('harness_validation',{}).get('passed') is True
                   and routed['harness_validation'].get('rtl_sha256')==row.get('rtl_sha256')
                   and routed['harness_validation'].get('harness_sha256')==routed.get('harness_sha256')
                   and evidence_integrity(routed['harness_validation'])=='verified'))
    return bool(harness_ok and row.get('passed') and row.get('max_abs_error', math.inf) <= error_limit
                and routed.get('stage') == 'routed' and routed.get('target') == target
                and routed.get('rtl_sha256') == row.get('rtl_sha256') and routed.get('passed')
                and evidence_integrity(routed) == 'verified' and resources_fit(m,target)
                and m.get('fully_constrained') is True
                and all(metric_number(m.get(k)) and m[k] >= 0 for k in ('setup_slack_ns','hold_slack_ns','pulse_slack_ns')))
