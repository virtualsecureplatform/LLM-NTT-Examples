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
