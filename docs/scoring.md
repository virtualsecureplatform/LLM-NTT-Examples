# Scoring

The benchmark uses a correctness-first scoring model. A candidate must pass the
task's evaluator before performance or resource metrics matter.

## Result Schema

`scripts/evaluate_candidate.sh` writes a JSON file with this shape:

```json
{
  "schema": "llm-ntt-evaluation-v1",
  "task_id": "hoge_streaming_intt_1024_p64",
  "mode": "verilator_test",
  "top_module": "INTTWrap",
  "correct": true,
  "build_passed": true,
  "test_passed": true,
  "lint_passed": false,
  "metrics": {
    "hoge_streaming_intt_input_cycles": 32,
    "hoge_streaming_intt_output_cycles": 32,
    "hoge_streaming_intt_max_wait_cycles": 65
  },
  "logs": {
    "configure": "build/eval/hoge_streaming_intt_1024_p64/configure.log",
    "build": "build/eval/hoge_streaming_intt_1024_p64/build.log",
    "test": "build/eval/hoge_streaming_intt_1024_p64/test.log"
  }
}
```

The exact metric keys depend on the task. All metrics printed by a test as:

```text
METRIC key=value
```

are copied into the result JSON.

## Correctness Gate

For `verilator_test` tasks:

```text
correct = build_passed && test_passed
```

For `lint_only` tasks:

```text
correct = lint_passed
```

A candidate with `correct = false` should receive score zero.

## Baseline Metrics

The extracted RTL is the baseline. Agents should compare candidates against the
baseline for the same task and toolchain.

Useful baseline values:

- input burst cycles
- output burst cycles
- wait cycles from input burst to first valid output
- total transaction cycles
- Verilator runtime
- synthesis resource use, if available

The evaluator currently records functional metrics and wall-clock build/test
time. Synthesis resource metrics are left as an extension point because Vivado
or another synthesis tool may not be available in the Apptainer image.

## Suggested Scalar Score

For automated ranking, use a scalar score only after correctness passes.

One simple latency-oriented score is:

```text
score = baseline_total_cycles / candidate_total_cycles
```

where:

```text
total_cycles = input_cycles + max_wait_cycles + output_cycles
```

For tasks that do not report `max_wait_cycles`, use the task-specific fixed wait
metric or mark latency score unavailable.

For resource-aware ranking:

```text
score = latency_score / resource_penalty
```

with:

```text
resource_penalty =
  0.35 * LUT_ratio +
  0.20 * FF_ratio +
  0.30 * DSP_ratio +
  0.15 * memory_ratio
```

where every ratio is candidate divided by baseline. The weights are only a
starting point; for FPGA NTT designs, DSP and memory pressure often deserve more
weight than FF count.

## Pareto Reporting

For architecture research, a Pareto frontier is more informative than one scalar
score. Keep all correct candidates and report nondominated points across:

- total latency cycles
- sustained throughput
- LUT
- FF
- DSP
- BRAM
- URAM
- fmax

If synthesis is unavailable, report a Verilator-only frontier using latency
cycles and code-level structural metrics, and label it clearly.

## Fairness Rules

- Do not change the C++ reference tests when comparing candidate designs.
- Do not change task manifests during a candidate run.
- Use the same TFHEpp submodule revision for every candidate.
- Use the same simulator and compiler version when comparing latency metrics.
- Separate simulation-only behavioral designs from synthesizable RTL.
- Report any task where only lint/interface checking is available.
