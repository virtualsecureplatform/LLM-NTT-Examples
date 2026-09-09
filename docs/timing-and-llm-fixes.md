# Timing and LLM acquisition follow-up

This follow-up addresses the timing and acquisition failures retained in the
[previous final report](final-plan-results.md). Measurements use the same
U280 part, Vivado 2023.2 and 4 ns clock as the corresponding preset baselines.
Earlier records remain separate; no failed result is promoted by changing a
clock constraint or replacing its RTL.

The [synthesis measurements](measured-evidence/timing-feedback/synthesis-report.md),
[128-point replay](measured-evidence/timing-feedback/replay128.json),
[256-point replay](measured-evidence/timing-feedback/replay256.json), and
[generic RTL preservation check](measured-evidence/timing-feedback/generic-preservation.json)
are published with their original records. Routed and fresh live validation
remain in progress.

## Resource-aware LLM feedback

Framework revision `0a5912e` makes the useful-discovery objective explicit:
correctness and timing do not compensate for exceeding resource caps. Each
observation now includes known resource feasibility, exceeded limits and missing
metrics. Failed/incomplete measurements do not become zero-resource samples.
The prompt requests a small calibration anchor, followed by gradual exploration
using measured headroom. It also receives the objectives and remaining budget.

Candidate advice uses only previously acquired observations from the matching
architecture family. It attempts the existing structural fit; with insufficient
data, LUT/FF/DSP replication scaling provides a deliberately labeled heuristic.
These extrapolations are not safe bounds and do not prune or remove candidates.
They cannot enter measured frontiers. There is no hidden reference-pool lookup
inside the ranking policy.

The replay CLI now supports `--sequential-llm`, re-ranking after each acquired
observation. The callback sees copies of legal configurations and acquired
metrics; the evaluator alone holds unobserved outcomes and reference IDs.
Regression tests cover that boundary, caller mutation, invalid selections,
missing measurements, and resource failures despite correct/timing-clean RTL.

```sh
python3 scripts/replay_search_policies.py --report build/policy128-reference-current/report.json --campaign campaigns/live-policy128.json --output-dir build/fresh-feedback-replay --budget 3 --seeds 2 3 4 --sequential-llm
```

`build/llm-feedback-sequential-replay` recovers 75% of the four-design N=128
reference frontier in each of three repetitions, with three feasible discoveries
per trial. The previous live study recovered 25%. This is initially replay
validation, not a fresh hardware improvement claim. Enumeration also recovers
75%, the maximum possible with three evaluations. Zero-temperature LLM calls
remain repetitions rather than independent random seeds.

A second-workload check, `build/llm-feedback-sequential-replay256`, recovers both
N=256 reference frontier designs in three evaluations, matching enumeration.
It is a finite-pool check, not evidence of general superiority. A fresh nine-
evaluation LLM study is prepared using isolated framework `0a5912e` and NGen
`997122d` checkouts. The generator executable is byte-identical to the original reference and control study, isolating the acquisition change. The launcher waits for the timing experiments to terminate.

## HOGE pipeline boundaries

The first critical path crossed factor lookup, a 64-bit multiply, modular
reduction, the transpose and the next radix level. Revision `9b31ab9` registers
factor/data inputs, four 32-bit partial products, two product-addition stages,
and Goldilocks reduction/correction. Valid tokens cross all nine stages.
Both transform directions pass the full oracle; forward overlap/reset/gap
verification passes 240 frames with a saturated 32-cycle interval.

The matched forward synthesis improves WNS from −8.937 to −1.920 ns, with
176563 LUT, 103519 FF and 1024 DSP. The matched inverse factor-only result is −3.838 ns with 135711 LUT, 62058 FF and 512 DSP. Both still fail setup. Transaction cycles
increase from 104 to 122 (inverse: 73 to 82). This is a real pipeline-depth
tradeoff, not a reduction in the transform's initiation rate.

The next critical path is the recursive constant shift plus butterfly. The
second implementation registers seven shift/reduction stages and two butterfly
stages per radix level. The former inverse split has its additional pre-shift
explicitly counted. Cycle tags and valid signals follow the same boundaries.
All 192 exponents are checked against independent modular exponentiation with
bubbles and reset; both complete transform oracles pass. Forward/inverse
transaction counts are 202/169, and the forward overlap test still passes 240
frames at interval 32. Forward synthesis now passes setup at +1.770 ns, using 209171 LUT, 273241 FF and 1024 DSP. Estimated hold slack is −0.075 ns, so this is not routed closure. Inverse synthesis also passes at +1.770 ns, using 171422 LUT, 241803 FF and 512 DSP; estimated hold is −0.112 ns. The first separate forward route completes with +0.280 ns setup slack but −0.680 ns hold slack (211201 LUT, 273327 FF, 1024 DSP). It fails timing qualification. A hold-path diagnostic is in progress; the failed measurement is retained.

## YATA arithmetic and conversion

The old `f300` microcoded profile inserted idle cycles around a combinational
lane. It now has seven registered arithmetic stages and commits a dependent
bundle on cycle eight. Tests compare all operation kinds with the original
signed/truncated arithmetic over 1200 cases. Baseline-profile RTL keeps its
original arithmetic schedule.

The 64-point full forward/inverse oracle passes. The first synthesis reduces
WNS from −5.805 to −1.574 ns, with 49713 LUT, 16020 FF and 80 DSP. Its transaction
count rises from 86 to 513 because dependent bundles wait for the registered
results. Timing still fails; the critical path has moved to output conversion.

The second implementation narrows counters and registers the output converter.
It retains the exact product bits that influence the rounded 32-bit torus word;
independent tests include negative representatives outside the canonical range,
bubbles and reset. Converter latency is reflected in directional wait metadata.
Input and output transpose overheads are also accounted for separately, fixing
the conservative eight-cycle overstatement for the large inverse task.

The 8-, 64- and 512-point arithmetic-lane implementations pass complete oracles.
The 512-point registered implementation needs 2609 inverse wait cycles. Its
watchdog is raised from 2000 to 4096; arithmetic comparisons and measured cycle
counts are unchanged. This admits a slower correct architecture without claiming
that it is faster. The 64- and 512-point output-pipeline oracles pass, as do 26 mid-operation reset checks followed by a complete transform in the opposite direction. Final synthesis passes setup at +1.282 ns, using 52340 LUT, 16403 FF and 80 DSP, with unchanged 513 worst-case transaction cycles. Estimated hold slack is −0.042 ns; the separate routed check remains pending.


## Routed confirmation contract

Fresh HOGE-forward and bidirectional YATA route checks use 4 ns, U280,
`BUFGCE_X0Y0`, 0.5–1.0 ns input arrival, 0–1.0 ns output requirements and two
preserved identity LUTs per output bit. The I/O reference is the existing input
cycle counter clock (`input_cycle_reg[0]/C`) for HOGE and the execution-state
clock (`core/executing_reg/C`) for YATA. All non-clock inputs, including reset,
and all outputs are constrained. The physical buffers count in utilization.

This is the same conditional neighboring-fabric modeling approach as the
[generic timing contract](fabric-timing-contract.md), using each native preset's
existing clock reference. It is not a board-shell measurement or a matched
routed comparison against extracted presets. Original zero-delay synthesis
records stay separate. Both setup and hold plus completed routing are required
before either new route can qualify.

## Functional regression and scope

NGen revision `64e2f9a` passes 158 Scala tests; the framework passes 138 Python
tests. Native and SGen-composed HOGE pipelines both pass complete forward and
inverse arithmetic checks, plus 240-frame forward overlap/gap/reset checks.
The seven previously measured generic designs regenerate byte-identical RTL
and identical cycle metadata, including the six N=128 policy configurations
and the qualified 16K/q54 architecture.

These changes repair preset setup timing at a substantial register and latency
cost. The extracted HOGE references remain better in the matched synthesis
area/transaction comparison. Improved setup slack does not establish a generator
performance win, and the conditional route checks do not establish board timing.
