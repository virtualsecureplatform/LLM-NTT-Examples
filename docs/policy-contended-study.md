# Completed policy study with hardware contention

This completed N=128 study uses four policies, seeds 2/3/4 and three fresh
evaluations per trial, with a 12-hour total budget. All 36 evaluations were
consumed. Scoring uses the complete six-architecture matched reference pool
with four feasible frontier designs. Each repetition observes at most three
designs, so its maximum frontier recall is 75%.

| Policy | Mean frontier recall | Range | Feasible discoveries (total / 9) | Failed evaluations |
| --- | ---: | ---: | ---: | ---: |
| enumerate | 75.0% | 75.0–75.0% | 9 / 9 | 0 |
| random | 50.0% | 50.0–50.0% | 6 / 9 | 1 |
| cost | 58.3% | 50.0–75.0% | 7 / 9 | 0 |
| llm | 25.0% | 25.0–25.0% | 3 / 9 | 0 |

| Policy | Seed | Trial wall seconds | Queue seconds | Frontier recall |
| --- | ---: | ---: | ---: | ---: |
| enumerate | 2 | 1212.05 | 950.427269 | 75.0% |
| random | 2 | 7533.99 | unknown | 50.0% |
| cost | 2 | 371.81 | 0.001371 | 50.0% |
| llm | 2 | 538.79 | 0.001309 | 25.0% |
| enumerate | 3 | 255.13 | 0.001310 | 75.0% |
| random | 3 | 400.10 | 0.001221 | 50.0% |
| cost | 3 | 265.83 | 0.001188 | 75.0% |
| llm | 3 | 524.66 | 0.001286 | 25.0% |
| enumerate | 4 | 252.33 | 0.001222 | 75.0% |
| random | 4 | 367.05 | 0.001411 | 50.0% |
| cost | 4 | 382.43 | 0.001171 | 50.0% |
| llm | 4 | 530.27 | 0.001227 | 25.0% |

The seed-2 random trial consumed one evaluation on a Vivado queue timeout.
Its old runner omitted the timeout duration, so total queue time remains
unknown rather than zero. Seed-2 enumeration also waited 950.43 seconds.
These scheduling effects confound elapsed time and recovery; this is not a
controlled policy-quality ranking. The other measurements match the reference
objective metrics; the missing timeout measurement is retained as a difference.

The LLM produced one resource-feasible candidate per repetition and two
candidates outside the declared resource caps. All its evaluated RTL passed
correctness and synthesis timing. Feasibility under caps is separate from
implementation success. Seeds do not control backend LLM randomness; these
zero-temperature calls are repetitions, not independent LLM random seeds.

The [separate replication](policy-uncontended-study.md) is complete: 36 successful evaluations, no metric differences from the reference, and 0.015637 seconds of total recorded queue wait. Both studies retained the same executable inputs.

Source: `build/policy-replication-sequence/contended-summary.json`. The published
[JSON](measured-evidence/policy-contended.json) retains per-trial metrics,
failures, measurement differences and source report hashes. Reproduce with:

```sh
python3 scripts/summarize_live_policy_trials.py --reference-dir build/policy128-reference-current --trials-dir build/live-policy128-three-seeds --output build/fresh-contended-summary.json
```
