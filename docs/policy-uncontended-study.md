# Completed policy replication

Follow-up: the [resource-aware LLM fix](timing-and-llm-fixes.md) now has nine fresh
passing evaluations and 75% frontier recovery in each repetition. The original
measurements and controls below remain unchanged.

The fresh N=128 replication completed all 36 evaluations: four policies, three repetitions (seeds 2/3/4), and three evaluations per trial within a 12-hour total budget. Every evaluation passed correctness and synthesis timing; all objective metrics match the six-architecture reference pool. Four reference designs meet the resource caps and lie on the frontier, so the three-evaluation budget limits recall to 75%.

| Policy | Mean frontier recall | Range | Feasible discoveries / 9 |
| --- | ---: | ---: | ---: |
| enumerate | 75.0% | 75.0–75.0% | 9 / 9 |
| random | 58.3% | 50.0–75.0% | 7 / 9 |
| cost | 58.3% | 50.0–75.0% | 7 / 9 |
| llm | 25.0% | 25.0–25.0% | 3 / 9 |

| Policy | Seed | Trial wall seconds | Queue seconds | Frontier recall |
| --- | ---: | ---: | ---: | ---: |
| enumerate | 2 | 245.80 | 0.001238 | 75.0% |
| random | 2 | 267.48 | 0.001173 | 75.0% |
| cost | 2 | 371.16 | 0.001175 | 50.0% |
| llm | 2 | 543.09 | 0.001424 | 25.0% |
| enumerate | 3 | 251.17 | 0.001096 | 75.0% |
| random | 3 | 411.23 | 0.001341 | 50.0% |
| cost | 3 | 268.79 | 0.001400 | 75.0% |
| llm | 3 | 530.23 | 0.001606 | 25.0% |
| enumerate | 4 | 253.10 | 0.001210 | 75.0% |
| random | 4 | 372.60 | 0.001291 | 50.0% |
| cost | 4 | 380.38 | 0.001423 | 50.0% |
| llm | 4 | 529.43 | 0.001260 | 25.0% |

Total recorded queue wait was 0.015637436 seconds, with no queue or execution timeout. The runner completed in 4429.76 seconds. The supervisor verified all 23 frozen executable hashes before and after the run; NGen was revision `997122d` for both studies and the reference pool. Main integration happened only after this sequence exited successfully.

The [original study](policy-contended-study.md) remains separate: random recall was 50% and one evaluation expired in the hardware queue. This replication removes that observed scheduling failure; it does not establish a general ranking from one small workload. Enumeration performs best here. The LLM repeats one feasible discovery per trial, with two otherwise correct candidates exceeding resource caps. Zero-temperature LLM calls are repetitions, not independent random seeds. The model was `unsloth/Qwen3.8-Flash-Next-GGUF:UD-IQ4_XS` at the supplied endpoint, with thinking disabled.

The [complete JSON](measured-evidence/policy-uncontended.json) records the campaign, per-trial costs, failures, metric comparisons and input hashes. Reproduce scoring with:

```sh
python3 scripts/summarize_live_policy_trials.py --reference-dir build/policy128-reference-current --trials-dir build/live-policy128-uncontended-three-seeds --output build/fresh-uncontended-summary.json
```
