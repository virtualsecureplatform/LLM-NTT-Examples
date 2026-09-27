from pathlib import Path

from scripts.report_fhe512_transpose_matrix import expected, rows


EVIDENCE = Path(__file__).resolve().parents[2] / 'docs' / 'measured-evidence'


def test_reduction_matrix_requires_every_boundary_combination():
    assert len(expected(('barrett',))) == 12
    all_reductions = ('barrett', 'montgomery', 'shoup')
    assert len(expected(all_reductions)) == 28
    assert {key[3:] for key in expected(all_reductions)} == {
        (reduction, transpose)
        for reduction in all_reductions for transpose in ('indexed', 'switch')}


def test_historical_barrett_evidence_is_complete_and_new_matrix_needs_more():
    files = [EVIDENCE / name for name in (
        'fhe512-covering.json', 'fhe512-switch-smoke.json', 'fhe512-switch-extension.json',
        'fhe512-structural-l2-indexed.json', 'fhe512-structural-l2-switch.json',
        'fhe512-structural-l4-indexed.json', 'fhe512-structural-l4-switch.json')]
    assert len(rows(files, prefer_later=True)) == 12
    try:
        rows(files, prefer_later=True, reductions=('barrett', 'montgomery', 'shoup'))
    except ValueError as error:
        assert 'missing configurations' in str(error)
    else:
        raise AssertionError('incomplete reduction matrix was accepted')
