# Integrated generator and architecture-search results

The four acceptance milestones in the [roadmap](ngen-sgen-search-roadmap.md)
are implemented, tested and measured. NGen main `d59d87a` integrates registered
memory issue, effective architecture metadata and HOGE constant specialization.
Framework main `c03f99c` integrates SGen HOGE composition, the overlap regression,
campaigns and complete queue-timeout duration accounting. SGen master `0f5a56d`
contains the square switch-transpose validity/frame-gap fix. The framework also
provides reproducible search, independent functional gates, multi-fidelity
measurement, constrained Pareto reporting, calibrated advisory cost models,
safe resource/bandwidth bounds, and LLM/enumeration/random/cost policies.

## Final validation

NGen main passes all 154 Scala tests and a fresh assembly. Framework main passes
all 134 Python tests with native tools enabled. The first framework test attempt
ran before assembly finished and correctly rejected a stale executable; its log
is retained in `/tmp/llm-final-main-tests.out`. The successful rerun is
`/tmp/llm-final-main-tests-rerun.out`. NGen's build log is
`/tmp/ngen-final-main-build.out`.

Fresh main generation preserves exact RTL hashes and timing declarations for:

- All six N=128 policy reference configurations, the qualified registered-issue
  N=16K/q54 route, and both HOGE shift directions: nine checks.
- The full 18-case FHE matrix: N=16K/64K/128K, q32/54/64, forward and inverse.
  Original candidate, campaign, oracle-result and verification-input hashes
  are checked before artifact comparison.
- Both SGen-composed HOGE directions, preserving the artifacts checked by the
  full transform oracles and the 240-frame forward overlap/reset/gap test.

Check scripts and results remain under `build/final-main-rtl-identity`,
`build/final-main-fhe-identity` and `build/final-main-composed-identity`.
Published JSON copies are [representative designs](measured-evidence/final-main-rtl-identity.json),
[FHE matrix](measured-evidence/final-main-fhe-identity.json) and
[composed HOGE](measured-evidence/final-main-composed-identity.json).
These checks establish preservation of previously validated artifacts; they
are not additional simulation runs or new hardware measurements.

A fresh `build/final-main-evidence-snapshot` revalidates artifact integrity and
recomputes qualification/frontiers for all six comparison groups. Its report
matches the [published snapshot](measured-evidence/report.json) exactly.
Original measurements, failed attempts and budget-limited outcomes remain
separate. The [integration archive](ngen-plan-integration.md) preserves the
combined HOGE oracle/overlap evidence outside the temporary worktree.

## Measured outcomes

At N=16384/q54 under the matched U280/Vivado 2023.2/4 ns fabric contract, both
NGen and the banked OpenNTT adapter pass routed setup and hold. NGen supports
3382.45 transforms/s versus 2541.92: 33.1% higher throughput and 25.9% lower
latency, using fewer FF/DSP but more LUT/BRAM. These are RTL-simulation rates
at a route-qualified clock, not board or memory-system throughput. All three
N=256 matched NGen/OpenNTT/modified-Proteus routes also qualify; each remains
on that workload's frontier. See [measurement tables](measured-evidence/report.md).

HOGE shifts save 55.6% DSP and 17.3% LUT in the forward ablation, but increase
FF and worsen setup slack. SGen composition alone has the same measured HOGE
resources and timing as pre-shift NGen. HOGE and YATA NGen candidates still fail
the 4 ns setup target; shorter simulated cycle counts are not hardware wins.
The stage-parallel HOGE inverse budget timeout remains unmeasured.

Both live policy studies completed 36 fresh evaluations using the same frozen
executable inputs. The [original study](policy-contended-study.md) retains its
queue timeout. The [clean replication](policy-uncontended-study.md) has no
failures, no objective-metric differences from the reference, and 0.015637 seconds
total queue wait. Mean frontier recovery is 75% for enumeration, 58.3% for random
and cost-guided selection, and 25% for the LLM. This does not establish an LLM
advantage. Three evaluations can recover at most three of four frontier designs;
zero-temperature LLM repetitions are not independent random seeds. Calibration
and architecture holdouts remain advisory, including unavailable structural fits.

## Scope of completion

The [acceptance map](roadmap-acceptance.md) ties every numbered criterion to
implementation and evidence. Completion covers the approved routed-RTL milestone
and architecture-search framework. It does not establish universal superiority
over the papers, HOGE/YATA timing closure, board execution, external-memory/RNS
system throughput, or a general policy ranking. Those remain research extensions,
with the negative measurements retained to guide subsequent work.
