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

For `lint_only` tasks, `correct = true` means interface elaboration only. It
does not mean the NTT arithmetic, coefficient order, latency, throughput, or
valid burst length has been checked. Do not mix lint-only tasks with
correctness-tested tasks in one scalar ranking; report them as tier0 interface
gates.

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

The evaluator records functional metrics and wall-clock build/test time. With
`--with-yosys`, it also runs a flattened Yosys structural estimate and adds
`yosys_*` metrics such as cell counts, wire bits, memory bits, and per-cell-type
counts. These are technology-independent RTL estimates, not post-place-and-route
FPGA resources.

With `--with-vitis`, the evaluator runs host Vivado/Vitis out-of-context RTL
synthesis for the task top and adds `vitis_*` metrics. Common normalized keys
include `vitis_lut`, `vitis_ff`, `vitis_dsp`, `vitis_bram_tile`, `vitis_uram`,
`vitis_timing_wns_ns`, and `vitis_fmax_mhz`; raw utilization rows are also kept
as `vitis_util_*` keys. The default target matches the AutoNTT examples: U280
part `xcu280-fsvh2892-2L-e` at `4.0 ns`. This selects the FPGA synthesis
target, not the candidate NTT architecture.

The LLM runner's `--goal hardware` mode is stricter than the default
correctness goal. It first applies a fast hardware-shape screen that rejects
simulation-style full-polynomial transform tasks, then requires
`vitis_synthesis_passed = true` and populated `vitis_*` resource metrics before
an attempt is considered successful. A candidate that passes Verilator but times
out or fails Vivado/Vitis remains a failed hardware attempt and is fed back to
the next generation attempt.

By default the hardware goal also enables Yosys as a technology-independent
structural estimate. `--no-yosys` may be used to skip that optional estimate
when Yosys flattening is the bottleneck; the hardware success criterion remains
Vivado/Vitis synthesis with populated `vitis_*` metrics.

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

Use `scripts/compare_autontt_metrics.py` to compute these ratios from two
standard evaluator result files:

```bash
scripts/compare_autontt_metrics.py \
  --reference build/autontt-compare/hoge-intt-reference/results.json \
  --candidate build/lab-hoge-bundle-intt-hardware/<timestamp>/eval/hoge_streaming_intt_1024_p64/results.json \
  --output build/autontt-compare/hoge-intt-comparison.json
```

The comparison JSON records correctness gates, per-prefix latency totals,
`baseline_total_cycles / candidate_total_cycles` latency scores, Vitis
resource ratios, timing ratios, the weighted resource penalty, and the
resource-aware score when both sides have the required metrics. If either side
lacks Vitis metrics, the resource score is reported as unavailable instead of
being inferred from stale baselines.

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

If `--with-yosys` is available, report a Yosys structural frontier separately
from vendor synthesis results. Yosys cell counts are useful for relative
screening, but they are not substitutes for LUT/FF/DSP/BRAM/fmax reports from a
target FPGA flow.

If `--with-vitis` is available, report that frontier separately from Yosys and
label the FPGA part and clock period. The checked-in scripts synthesize RTL
out-of-context, so these numbers are reference post-synthesis estimates rather
than routed accelerator-link results.

## Fairness Rules

- Do not change the C++ reference tests when comparing candidate designs.
- Do not change task manifests during a candidate run.
- Use the same TFHEpp submodule revision for every candidate.
- Use the same simulator and compiler version when comparing latency metrics.
- Separate simulation-only behavioral designs from synthesizable RTL.
- Report any task where only lint/interface checking is available.
- Do not treat planned manifests under `tasks/planned/` as executable
  benchmark tasks until a Verilator harness and task manifest are promoted.
