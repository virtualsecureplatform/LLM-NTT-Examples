from architecture_search import wide_products as wide
from scripts.fhe512_sgen_precision import corpus, measured_error
from scripts.fhe512_preroute import configuration_name


def test_precision_grid_names_and_distinct_rtl_choices():
    w=wide.workload(512,2147483647,'negacyclic',1<<32)
    configs=wide.candidates(w,dict(generators=['sgen'],sgen_backends=['compact'],lanes=[2],
                                   fractional_bits=[30,32],guard_bits=[0],
                                   omit_low_diagonals=[0,1,2]))
    assert len(configs)==len({configuration_name(c) for c in configs})==6
    assert {(c['fractional_bits'],c.get('omit_low_diagonals',0)) for c in configs}=={
        (fraction,omitted) for fraction in (30,32) for omitted in (0,1,2)}


def test_omission_error_metrics_match_independent_oracle():
    w=wide.workload(16,2147483647,'negacyclic',1<<32)
    vectors=corpus(w)
    assert len(vectors)==3
    assert measured_error(w,vectors,0)['observed_max_abs_error']==0
    for omitted in (1,2):
        result=measured_error(w,vectors,omitted)
        assert 0<result['observed_max_abs_error']<=wide.omission_error_bound(w,omitted)
        assert result['samples']==16*len(vectors)
