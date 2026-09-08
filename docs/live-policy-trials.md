# Sequential policy trials with fresh measurements

`run_live_policy_trials.py` evaluates policies through the real generator,
independent RTL oracle, and synthesis path. It does not replay a saved pool.

```sh
python3 scripts/run_live_policy_trials.py --campaign campaigns/live-policy128.json --output-dir build/live-policy128-trials --evaluations 2 --seeds 1 --hours 12
```

Each policy selects one remaining legal configuration. The normal search CLI
validates that exact selection against the declared space, generates RTL, runs
correctness, and synthesizes only a passing design. Only then does the controller
reveal the observation for the next acquisition. A failed measurement consumes
an evaluation but supplies no invented resource metrics. LLM endpoint failures
stop that trial and are recorded separately; they are not scored as random
fallbacks. Requests/responses include only legal choices and prior observations.

Enumeration uses canonical configuration order. Random shuffles the remaining
choices with the seed at each acquisition. Cost uses the same seeded cold start,
then nearest-neighbor LUT predictions from available observations, with every
fourth step reserved for exploration. This initial online cost policy is distinct
from the separately pretrained structural model. No policy receives measurements
from another policy's run. Trials repeat actual generation and evaluation even
when they select the same architecture.

The manifest records source identities and hashes of executable dependencies.
Each child evaluation has the ordinary source/tool/binary manifest and a
configuration file. The trial records selection time, total elapsed time, vendor
queue time, failures, observed metrics, and the observed synthesis frontier.
Executable-input changes stop acquisition rather than silently mixing code.
These initial trial runs require a fresh directory; the child search runner
retains its own normal strict resume behavior.

The supplied N=128/q32 workload differs from the earlier measured N=256 policy
pool. It searches PE=1,2,4 and stage-groups=1,2. The initial four-policy,
one-seed/two-evaluation run uses eight fresh candidate evaluations. It is an
execution pilot, not a statistically conclusive policy comparison. Shared
vendor queue contention confounds wall-time comparisons, and full-frontier
recall cannot be claimed without a complete same-workload reference pool.
