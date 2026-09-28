from scripts.report_fhe512_common_frontier import frontier


def point(name, error=0, cells=10, memory=10, interval=10):
    return dict(name=name, passed=True, max_abs_error=error, cells=cells,
                memory_bits=memory, register_bits=10, multipliers=1,
                latency_cycles=10, initiation_interval_cycles=interval)


def test_tradeoffs_ties_and_error_budget():
    rows = [point('exact'), point('equal'), point('slower', interval=11),
            point('smaller-but-inexact', error=8, cells=8),
            point('smaller-memory', memory=8, interval=11)]
    assert frontier(rows) == ['exact', 'equal', 'smaller-but-inexact', 'smaller-memory']
    assert frontier(rows, 0) == ['exact', 'equal', 'smaller-memory']
    assert frontier(rows, 7) == frontier(rows, 0)
