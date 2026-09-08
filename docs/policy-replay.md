# Equal-budget policy replay

`replay_search_policies.py` compares rankings over a frozen pool of completed,
independently correct hardware measurements. Each acquired candidate consumes
one evaluation, including a timing failure or a resource-limit violation.
Policies only receive legal configurations and already acquired outcomes;
full-pool outcomes are used by the evaluator to score frontier recovery.

```sh
python3 scripts/replay_search_policies.py --report build/ngen-mont7-threeway256/report.json --campaign campaigns/threeway256-synthesis.json --output-dir build/replay-example --budget 2 --seeds 1 2 3 --llm
```

Enumeration uses canonical configuration order. Random uses seeded permutations.
The online cost prototype predicts LUT cost from acquired neighbors and reserves
every fourth selection for exploration. This adaptive prototype differs from
the production CLI's static ranking with a separately trained cost model. LLM
ranking receives configurations, workload, target, resource limits, and objectives;
its request and response are saved. Endpoint failures remain separate failures,
not mislabeled random-policy results.

The report records feasible discoveries, recovery of the full-pool Pareto
frontier, per-step IDs, and prediction errors before measurements are revealed.
Duplicate configurations with different implementation revisions are rejected.
Missing hardware metrics are rejected, not imputed as zero.

This is an offline finite-pool comparison. It does not measure end-to-end search
wall time, functional-failure discovery, or generalization to unseen designs.
The first three-point smoke test gave every policy two-thirds frontier recall
at budget two; all three points were nondominated. It validates the machinery
and live LLM calls, and provides no evidence of policy superiority.

`campaigns/policy-pool256-fabric.json` adds PE counts one and four with one/two/four
stage groups, under the shared fabric contract. Its explicit LUT, FF, DSP, and
BRAM limits make feasible-candidate discovery relevant. The new measurements
must finish before reporting a larger policy comparison. Online end-to-end
policy trials and held-out workload evaluation remain acceptance work.

The six-candidate pool exposed a measurement-driver failure after Vivado had
written its checkpoint: a workspace shell-script edit during the vendor call
caused Bash to resume at the wrong location. New hardware jobs copy the driver
and its Tcl helper into their result directory before execution. The failed
PE=4/groups=2 attempt is retained; a fresh campaign in
`build/policy-pool256-driver-retry` re-evaluates that configuration. Do not treat
this tool failure as measured timing failure or fill its missing metrics.

The replay validator now accepts the search runner's `hardware_failed` status
when implementation actually completed and all required measurements exist.
This allows real timing failures to consume budget without entering the
frontier. Incomplete implementation and missing metrics remain rejected.

## Five completed measurements

`build/policy-pool256-completed-five.json` records the original report hash and
the excluded PE=4/groups=2 driver failure. It contains PE=1/groups=1,2,4 and
PE=4/groups=1,4. This conditional pool is not the complete six-point experiment.
With limits LUT=10000, FF=6000, DSP=50, BRAM=8, only PE=1/groups=1,2 are feasible;
both belong to the reference frontier.

The saved replay `build/policy-replay256-five` uses budget three and seeds 1–5.
All five live LLM calls succeeded; requests and responses are retained.

| Policy | Mean frontier recall | Mean feasible discoveries |
| --- | ---: | ---: |
| Enumeration | 1.00 | 2.0 |
| Random | 0.50 | 1.0 |
| Online cost | 0.70 | 1.4 |
| LLM | 1.00 | 2.0 |

The LLM ties enumeration here. These small, overlapping finite-pool trials do
not demonstrate generalization or an LLM advantage over enumeration. The LLM
uses temperature zero and does not receive the random seed, so its repeated
calls are not independent seeded exploration trials.

`build/policy-pool256-five-cost.json` reports five-sample leave-one-out mean
absolute errors: LUT 10526.20, FF 2314.50, DSP 47.29, and BRAM 8.57. This simple
nearest-neighbor model is unsuitable for resource pruning on this sample.
Zero WNS error reflects identical +0.599 ns estimates at all five points and
provides no evidence of general timing prediction. Stronger structural models
and held-out measurements remain necessary.

## Structural resource model

`calibrate_architecture_cost.py --method structural` fits fixed overhead,
stage-group count, and PE count times stage-group count. It only combines
matching streamed radix-2 configuration families within the existing exact
workload/target check. Insufficient or rank-deficient observations yield an
unavailable prediction; timing prediction is unsupported. The production
`--policy cost --cost-model ...` path honors the saved model method. Neither
model supplies safe pruning bounds.

On the same five completed measurements, leave-one-out MAE is LUT 1977.67 and
FF 395.98; DSP and BRAM errors are below numerical precision. Results are in
`build/policy-pool256-five-structural-cost.json`. The model was also checked
against the separately measured PE=2/groups=1 synthesis from
`build/ngen-mont7-fabric256/report.json`, excluded from training by configuration
and RTL identity. `build/policy-pool256-structural-heldout.json` records hashes,
predictions, and outcomes:

| Metric | Prediction | Measured | Absolute error |
| --- | ---: | ---: | ---: |
| LUT | 6281.36 | 4841 | 1440.36 |
| FF | 1768.50 | 1735 | 33.50 |
| DSP | 22 | 22 | < 1e-10 |
| BRAM | 5.33 | 4 | 1.33 |

This is one held-out architecture under the same workload, not an unseen-workload
test. In particular, the BRAM mismatch shows that a smooth replication fit does
not capture every memory-banking discontinuity. The stronger model improves
these resource estimates but does not justify discarding unmeasured candidates.
