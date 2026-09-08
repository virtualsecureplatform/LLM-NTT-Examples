# Roadmap acceptance evidence

This maps the four numbered milestones in
[the roadmap](ngen-sgen-search-roadmap.md#implementation-milestones-and-acceptance-criteria)
to concrete evidence. It supplements the chronological
[completion audit](plan-completion-audit.md). The final integration and policy
results are recorded in [the final report](final-plan-results.md).

| Roadmap criterion | Evidence inspected | State / remaining work |
| --- | --- | --- |
| 1: two distinct legal implementations pass the unchanged oracle | `build/preset-hoge-forward-validation/report.json` and inverse counterpart each contain four distinct RTL artifacts, three correct; the historical fourth failure remains recorded | Demonstrated; later stage-parallel repairs have separate records |
| 1: recorded commands reproduce candidates | Candidate generation commands, source/binary identities and embedded NGen build checks; fresh registered-issue metadata validation reproduces the routed 16K RTL hash | Demonstrated; assembled main preserves all nine representative RTL/timing identities |
| 1: failed/lint results cannot enter functional frontier | `search.py` requires an independently correct `verilator_test` for presets; `test_architecture_search.py::test_evidence_gates` rejects failed/lint evidence | Implemented and tested |
| 1: missing synthesis is not a resource score; declarations remain separate | Separate stage frontiers in search reports; cost predictions cannot become evidence; preset `declared` metadata is separate from `evaluation.metrics` | Implemented and tested; no promotion of unmeasured hardware |
| 2: square, rectangular, linear ordering/reset/frame-gap checks | Five square widths, twelve rectangular shapes and eight linear configurations in the permutation validation records | Demonstrated under their documented, different protocols |
| 2: composed complete NTT oracle and reproducible generator identities | All three YATA switch/stride candidates pass in `build/yata8x8-permutation-comparison`; HOGE-SGen forward also passes on branch `hoge-sgen-namespaces` | Integrated; both HOGE directions and 240 overlapping forward frames pass; main reproduces both composed RTL artifacts exactly |
| 2: count full adapter resources and latency | YATA three-option synthesis includes wrappers and reports 86/86/96 cycles; all three fail setup and remain excluded | Measured; HOGE composition also measured: same resources and failed setup as pre-shift NGen |
| 3: independent stage parallelism and actual timing hazards | Generic PE/radix/stage-group capability checks; scheduler/arithmetic regression suites; all 18 registered-issue FHE oracles | Demonstrated; registered issue and effective metadata are integrated in NGen main |
| 3: identical-workload ablation for improvements | Separated 16K control-ROM/product/registered-issue records; compact-address, Kyber storage and YATA conversion comparisons | Completed ablations documented; HOGE forward shift ablation complete: fewer DSP/LUT, more FF and worse setup slack |
| 3: measured benefits and visible tradeoffs | Matched N=16K registered-issue route and OpenNTT both qualify; NGen trades more LUT/BRAM for lower latency and fewer FF/DSP | Demonstrated for that workload; no universal dominance claim |
| 4: calibrated models and resource/bandwidth pruning | Six-point N=128 integrity-checked calibration, leave-one-out and whole-architecture holdouts; bandwidth/issue and state-capacity bound tests | Demonstrated; structural group holdouts are unavailable, predictions remain advisory |
| 4: correct candidates, matched baselines and routed results | Integrity-rechecked snapshot contains three qualified N=256 routes and two qualified N=16K routes; baseline adapters and modified Proteus are labeled | Demonstrated for those matched workloads |
| 4: model error, search cost and policy comparison | Cost holdout reports and completed live pilot/replay retain negative LLM outcomes | Both 36-evaluation studies complete; clean replication has no failures and 0.015637 seconds total queue wait |
| 4: final reproducible comparison report and limited claims | Published snapshot covers six completed groups; HOGE forward explicitly favors the reference on timing qualification | Complete; negative HOGE/LLM outcomes, both policy studies and integrated revision identities are retained |

All 23 frozen executable inputs were checked before and after the clean policy
replication. Both studies and their supervisor terminated before integration.
NGen main `d59d87a` and framework main `c03f99c` contain the tested branches.
Final main passes 154 Scala tests and 134 Python tests. Fresh generation checks
preserve the measured RTL and timing declarations; the original full-oracle
and hardware records remain the evidence, rather than new hardware claims.
See [the final report](final-plan-results.md) for preservation bundles and limits.

The four numbered acceptance milestones are covered by the evidence above.
Board execution remains deferred. Wider workload sampling, HOGE/YATA timing
closure, RNS/memory-system expansion and universal superiority are not established
by this routed-RTL milestone.
