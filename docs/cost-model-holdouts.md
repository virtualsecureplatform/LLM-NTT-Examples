# Architecture-level cost-model validation

The completed `build/policy128-reference-current` pool contains all six PE=1/2/4,
stage-groups=1/2 configurations for the same N=128/q32 workload and U280 4 ns
synthesis target. All six hardware records pass the new artifact-integrity
checks. This is a fresh complete pool; it is not mixed with older revisions or
another workload's fitted coefficients.

Leave-one-out mean absolute errors:

| Metric | Three-neighbor model | Structural replication model |
| --- | ---: | ---: |
| LUT | 3899.66 | 1415.81 |
| FF | 930.86 | 70.77 |
| DSP | 17.50 | 1.69 |
| BRAM | 2.70 | 1.93 |

All URAM observations are zero and synthesis WNS is constant, so their small or
zero errors do not validate prediction on other designs. The structural model
does not predict timing.

`validate_cost_holdouts.py` removes an entire PE or stage-group level from the
training set, then predicts only the withheld designs. It asserts disjoint RTL
identities, records training/validation hashes, and reports unavailable fits
separately from error. The corresponding LUT results are:

| Withheld level | Nearest LUT MAE | Structural LUT MAE | Structural coverage |
| --- | ---: | ---: | --- |
| PE=1 | 4632.92 | 2190.05 | 2/2 |
| PE=2 | 2106.67 | 1461.80 | 2/2 |
| PE=4 | 9534.03 | 4462.25 | 2/2 |
| Groups=1 | 5299.70 | unavailable | 0/3 |
| Groups=2 | 5402.51 | unavailable | 0/3 |

The group-held-out training data has only one group count and cannot identify
all structural coefficients. Returning unavailable avoids presenting an
underdetermined extrapolation as measured accuracy. PE=4 extrapolation also
shows that the lower leave-one-out error is not a reliable resource bound.
Both models remain advisory; analytical safe bounds continue to handle pruning.

Reproduce the holdouts:

```sh
python3 scripts/validate_cost_holdouts.py --campaign campaigns/live-policy128.json --reports build/policy128-reference-current/report.json --output build/new-cost-holdouts.json
```

The completed artifact is
`build/policy128-reference-current/architecture-holdouts.json`; adjacent
`nearest-cost.json` and `structural-cost.json` contain calibration and
leave-one-out results. The live acquisition trial retains its frozen nearest-
neighbor cost policy. This offline validation does not change a policy midway
through its experiment or supply withheld data to it.
