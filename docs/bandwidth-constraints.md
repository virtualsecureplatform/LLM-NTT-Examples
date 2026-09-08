# Throughput requirements and bandwidth bounds

Generic campaigns accept an optional contract:

```json
{
  "requirements": {"min_transforms_per_second": 500000},
  "bandwidth": {
    "input_bits_per_second": 16000000000,
    "output_bits_per_second": 16000000000,
    "coefficient_bits": 32
  }
}
```

Input and output limits apply independently. An optional
`shared_bits_per_second` instead/additionally limits the combined input/output
traffic. Each transform transfers N input and N output coefficients; shared
traffic therefore costs 2*N*coefficient_bits. Transport width defaults to the
modulus bit length, may include padding, and cannot be smaller than the field.
These are declared service limits, not measured board bandwidth. Compression,
reuse across transforms, and resident multi-operation pipelines require a
different execution boundary and are not represented by this contract.

Before generation, the search computes optimistic throughput ceilings from:

- The registered interface, at most one lane vector per cycle.
- Radix-2 streamed butterfly issue capacity: at least one stage group has
  ceil(log2(N)/groups) stages, each requiring N/2 butterflies, with at most PE
  issues per cycle.
- Each declared independent or shared transport limit.

A configuration is pruned only if the smallest ceiling is strictly below the
required rate. The record includes the bound and reason with mode `bound` and
status `pruned`; it receives no correctness or implementation evidence and
consumes no functional/hardware evaluation budget. This necessary-condition
test omits real overheads and cannot certify feasibility. It also does not
replace FPGA resource constraints or supply resource-cost lower bounds.

Reports retain measured `transforms_per_second` at the core boundary. They
add `bandwidth_capped_transforms_per_second`, capped by the transport limit, for
hardware Pareto ranking under this contract. The minimum required rate is a
separate necessary-condition eligibility gate, alongside correctness, implementation timing, and
resource limits. The capped rate assumes ideal overlap and is not a measured
end-to-end service rate; host scheduling and transfer stalls can lower it. Replay policies use the same capped objective and minimum;
LLM requests include the requirements and bandwidth contract. A hardware run
with no qualifying frontier exits unsuccessfully. Simulation-only runs verify
correctness, not achievement of the throughput requirement.

`campaigns/bandwidth-pruning256.json` provides an executable example.
`build/bandwidth-pruning256-validation` records PE=1 as pruned (244140.625/s
optimistic ceiling versus 500000/s required), and PE=4 as functionally passing.
Its state records one functional evaluation. The report does not claim PE=4
meets the required rate without implementation evidence.

All six previously measured PE/stage-group pool points obey their analytical
ceilings (`build/policy-pool256-throughput-bound-check.json`). The replay in
`build/bandwidth-capped-policy-replay256` also applies the combined bandwidth, minimum
rate, and resource limits to measured candidates. Validation covers shared-link
traffic, coefficient padding, exact-bound equality, budget-free exclusion,
retention of raw core metrics, and minimum-rate frontier/replay behavior.
