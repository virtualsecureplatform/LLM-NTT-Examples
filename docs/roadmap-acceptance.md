# Roadmap acceptance evidence

This maps the four numbered milestones in
[the roadmap](ngen-sgen-search-roadmap.md#implementation-milestones-and-acceptance-criteria)
to concrete evidence. It supplements the chronological
[completion audit](plan-completion-audit.md); it does not certify completion.
Experimental branches still need integration, pending measurements must finish,
and the live policy comparison must be reported before the final audit.

| Roadmap criterion | Evidence inspected | State / remaining work |
| --- | --- | --- |
| 1: two distinct legal implementations pass the unchanged oracle | `build/preset-hoge-forward-validation/report.json` and inverse counterpart each contain four distinct RTL artifacts, three correct; the historical fourth failure remains recorded | Demonstrated; later stage-parallel repairs have separate records |
| 1: recorded commands reproduce candidates | Candidate generation commands, source/binary identities and embedded NGen build checks; fresh registered-issue metadata validation reproduces the routed 16K RTL hash | Demonstrated for recorded checks; repeat final assembled-main smoke checks after integration |
| 1: failed/lint results cannot enter functional frontier | `search.py` requires an independently correct `verilator_test` for presets; `test_architecture_search.py::test_evidence_gates` rejects failed/lint evidence | Implemented and tested |
| 1: missing synthesis is not a resource score; declarations remain separate | Separate stage frontiers in search reports; cost predictions cannot become evidence; preset `declared` metadata is separate from `evaluation.metrics` | Implemented and tested; no promotion of unmeasured hardware |
| 2: square, rectangular, linear ordering/reset/frame-gap checks | Five square widths, twelve rectangular shapes and eight linear configurations in the permutation validation records | Demonstrated under their documented, different protocols |
| 2: composed complete NTT oracle and reproducible generator identities | All three YATA switch/stride candidates pass in `build/yata8x8-permutation-comparison`; HOGE-SGen forward also passes on branch `hoge-sgen-namespaces` | YATA integrated; both HOGE directions and 240 overlapping forward frames pass on prepared integration branches; main integration pending |
| 2: count full adapter resources and latency | YATA three-option synthesis includes wrappers and reports 86/86/96 cycles; all three fail setup and remain excluded | Measured; HOGE composition also measured: same resources and failed setup as pre-shift NGen |
| 3: independent stage parallelism and actual timing hazards | Generic PE/radix/stage-group capability checks; scheduler/arithmetic regression suites; all 18 registered-issue FHE oracles | Demonstrated; registered-issue branch integration pending |
| 3: identical-workload ablation for improvements | Separated 16K control-ROM/product/registered-issue records; compact-address, Kyber storage and YATA conversion comparisons | Completed ablations documented; HOGE forward shift ablation complete: fewer DSP/LUT, more FF and worse setup slack |
| 3: measured benefits and visible tradeoffs | Matched N=16K registered-issue route and OpenNTT both qualify; NGen trades more LUT/BRAM for lower latency and fewer FF/DSP | Demonstrated for that workload; no universal dominance claim |
| 4: calibrated models and resource/bandwidth pruning | Six-point N=128 integrity-checked calibration, leave-one-out and whole-architecture holdouts; bandwidth/issue and state-capacity bound tests | Demonstrated; structural group holdouts are unavailable, predictions remain advisory |
| 4: correct candidates, matched baselines and routed results | Integrity-rechecked snapshot contains three qualified N=256 routes and two qualified N=16K routes; baseline adapters and modified Proteus are labeled | Demonstrated for those matched workloads |
| 4: model error, search cost and policy comparison | Cost holdout reports and completed live pilot/replay retain negative LLM outcomes | All 36 original observations complete and summarized with contention caveats; equal-budget replication without competing jobs is running |
| 4: final reproducible comparison report and limited claims | Published snapshot covers six completed groups; HOGE forward explicitly favors the reference on timing qualification | Inverse and composed HOGE measurements complete with negative outcomes retained; consolidate policy results and integrated revision identities |

The live policy manifest was rechecked against all 23 executable inputs after
main documentation updates and isolated experiments: no hash changed. Main
NGen and the framework implementation therefore remain fixed for that run.

Final integration must preserve the measured artifact identities. A changed
RTL artifact needs new corresponding evidence; a metadata-only difference can
use exact RTL hash equality with the retained measurement. Tests alone do not
establish a hardware improvement. The deferred board-execution step remains
outside the approved routed-RTL milestone.

## Remaining execution order

1. Forward constant-shift synthesis is complete and consolidated with
   pre-shift NGen, SGen-composed and extracted HOGE forward records.
2. The original live-policy run is complete. Its queue failure consumes
   evaluation budget and remains visible in the published contention report.
3. Repeat the same 36 fresh evaluations (four policies, seeds 2/3/4, three
   evaluations each, 12-hour total budget) without competing hardware campaigns.
   Reuse the complete reference pool only for scoring; do not reuse its
   measurements as live observations. Keep the same executable inputs for
   direct comparability. Record both studies separately.
4. Integrate the tested NGen and framework branches into main, rebuild NGen,
   verify measured RTL identities and run the appropriate final checks.
5. Publish the consolidated evidence and policy summaries, then re-audit every
   criterion above against the integrated sources and retained artifacts.

The prepared framework integration `cecaa91` passes all 133 Python tests; the
prepared NGen integration `f4032e9` passes 154 Scala tests. These are pushed
branches, not a claim that final main integration or this acceptance audit is
complete. The clean policy replication is necessary because an observed queue
timeout in the current run reflects contention, not acquisition quality.
