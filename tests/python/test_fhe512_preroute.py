from scripts.fhe512_preroute import (centered_error, configuration_name, configurations,
                                    pareto, quantization_points, quantize, quantized_rtl)
from architecture_search import wide_products as wide


def test_quantization_wrap_and_bound():
    for bits in (0, 1, 4, 8):
        for value in (0, 1, 7, 8, 15, (1 << 32) - 8, (1 << 32) - 1):
            actual = quantize(value, bits)
            assert 0 <= actual < 1 << 32
            assert abs(centered_error(actual, value)) <= ((1 << (bits - 1)) if bits else 0)


def test_screening_frontier_keeps_error_area_tradeoff():
    rows = [
        dict(name='exact', passed=True, max_abs_error=0, yosys_cells=100,
             latency_cycles=10, initiation_interval_cycles=5),
        dict(name='approx', passed=True, max_abs_error=8, yosys_cells=80,
             latency_cycles=10, initiation_interval_cycles=5),
        dict(name='dominated', passed=True, max_abs_error=8, yosys_cells=120,
             latency_cycles=11, initiation_interval_cycles=6),
    ]
    assert pareto(rows) == ['exact', 'approx']


def test_quantized_wrapper_has_two_lanes():
    w = wide.workload(16, 7, 'negacyclic', 1 << 32)
    rtl = quantized_rtl('module SearchTop; endmodule\n', w, 4)
    assert 'module ExactProduct' in rtl
    assert rtl.count('module SearchTop') == 1
    assert 'out_data[31:0]' in rtl and 'out_data[63:32]' in rtl


def test_covering_grid_is_distinct_and_budgeted():
    w = wide.workload(512, 2147483647, 'negacyclic', 1 << 32)
    configs = configurations(w, False, 'covering')
    assert len(configs) == len(set(map(configuration_name, configs))) == 18
    assert sum(quantization_points(c, 4, 'covering') for c in configs) == 4
    assert {c['backend'] for c in configs} == {'streamed', 'stage-parallel'}
    assert {c['reduction'] for c in configs} == {'barrett', 'montgomery', 'shoup'}


def test_switch_transpose_is_a_distinct_search_axis():
    w = wide.workload(512, 2147483647, 'negacyclic', 1 << 32)
    configs = configurations(w, False, 'smoke', ('indexed', 'switch'))
    assert len(configs) == len(set(map(configuration_name, configs))) == 4
    assert [c.get('transpose', 'indexed') for c in configs] == ['indexed', 'switch'] * 2
