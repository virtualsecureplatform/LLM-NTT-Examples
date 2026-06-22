# AutoNTT Adapter Notes

AutoNTT and this repository are complementary:

- AutoNTT searches HLS NTT accelerator architectures and emits TAPA/Vitis HLS.
- This repository provides small RTL/Verilator tasks with TFHEpp references and
  fixed top-level Verilog contracts.

The best direct overlap is the HOGE `N = 1024`, 64-bit-prime setting. YATA is
still useful as an LLM RTL-generation task, but it is not a direct AutoNTT input
because the extracted YATA example uses `N = 512`, while AutoNTT's documented
range starts at `N = 1024`.

## Mapping HOGE To AutoNTT

HOGE streaming INTT task:

```text
LLM-NTT task: hoge_streaming_intt_1024_p64
AutoNTT poly_size: 1024
AutoNTT mod_size: 64
Prime: 0xffffffff00000001
Interesting reduction: custom pseudo-Mersenne reduction
Architectures: iterative, dataflow, hybrid
```

Example AutoNTT command shape:

```bash
cd ../AutoNTT/automation_framework
python3 AutoNTT.py \
  --poly_size 1024 \
  --mod_size 64 \
  --resources fpga_resources.json \
  --arch_type IDH \
  --modmul_type C \
  --custom_mod_kernel ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_kernel.txt \
  --custom_mod_host ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_host.txt
```

AutoNTT emits HLS, not the exact RTL top modules expected by this repository.
To compare an AutoNTT result against these tasks, add a wrapper that adapts the
AutoNTT generated interface to the task manifest's Verilog ports and stream
ordering.

## What To Compare

Useful comparisons:

- AutoNTT iterative vs HOGE extracted streaming RTL.
- AutoNTT dataflow vs HOGE extracted streaming RTL.
- Barrett vs Montgomery vs WLM vs HOGE pseudo-Mersenne custom reduction.
- Different butterfly-unit budgets under the same resource file.
- Different target latency or throughput constraints.
- Verilator latency metrics vs optional `--with-yosys` structural cell counts
  before running a vendor FPGA flow.

Use correctness-tested HOGE tasks for these comparisons. The extracted
`hoge_streaming_ntt_1024_p64` task is lint-only and should remain an interface
gate; use `hoge_externalproduct_ntt_1024_p64` for HOGE forward NTT arithmetic
and latency comparisons.

## YATA Gap

YATA has two properties that make it valuable for LLM-based RTL search even
though it is not a direct AutoNTT fit:

- `N = 512`, smaller than AutoNTT's documented range.
- signed 27-bit compressed RAINTT arithmetic with `P = 5^4 * 2^16 + 1`.

Possible extensions:

- Add an AutoNTT small-N mode for `N = 512`.
- Add a custom signed reduction model compatible with YATA's RAINTT arithmetic.
- Treat YATA as the RTL-only benchmark and HOGE as the AutoNTT-aligned
  benchmark.

## Integration Boundary

Keep the boundary explicit:

- AutoNTT is the architecture-search engine.
- `tasks/*.json` are the benchmark problem statements.
- `scripts/evaluate_candidate.sh` is the correctness and metrics oracle.
- Candidate adapters are responsible for matching top-level ports and stream
  ordering.
- Planned manifests under `tasks/planned/` describe future targets and are not
  evaluator-ready tasks.

## LLM RTL Generator

This repository also includes an AutoNTT-style LLM candidate generator:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --endpoint lab \
  --strategy behavioral_reference \
  --attempts 1
```

The generator does not import AutoNTT's HLS backend. Instead, it uses the same
architecture knobs as prompt variables: iterative/dataflow/hybrid family,
parallelism, radix, buffering, twiddle strategy, and modular multiplication
choice. It then writes candidate Verilog into `build/llm-runs/` and can call
`scripts/evaluate_candidate.sh` for the selected task.

`--endpoint lab` reads the private OpenAI-compatible endpoint from
`LLM_NTT_LAB_ENDPOINT`; pass a full endpoint URL or set `LLM_NTT_LLM_ENDPOINT`
when using a different server.
The identity task is a correctness-scored smoke test for the full endpoint,
Verilog extraction, and prepared-evaluator loop, but it is not evidence of
functional NTT generation because a direct identity implementation can pass.
Use `hoge_streaming_intt_1024_p64` or `hoge_externalproduct_ntt_1024_p64` for
real arithmetic-generation runs.

Use `--plan-only` to inspect the generated search points. Use
`--strategy behavioral_reference` to produce simulation-first candidates that
should be reported separately from hardware-quality RTL.

Use `--candidate-source reference` to copy the task's extracted golden RTL into
the same AutoNTT-style run directory and evaluate it as a functional baseline:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source reference \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

Reference-seeded runs are useful for generating known-good results and checking
the evaluator path. They should remain distinct from endpoint-generated RTL
results when comparing AutoNTT-style search points.

Use `--candidate-source chisel_reference` when the reference RTL should be
generated from the checked-in Chisel source rather than copied from an existing
Verilog artifact:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --candidate-source chisel_reference \
  --goal hardware \
  --no-yosys \
  --vitis-timeout 300
```

The runner copies the task's `variants/<variant>/chisel` project to `/tmp`, runs
`sbt run`, and evaluates the emitted top-level Verilog. If host `sbt` is not
available, it uses the configured Apptainer image. This path is useful for
synthesizable reference baselines and for proving the hardware evaluator path,
but it is still a reference-source run, not novel LLM-written RTL.

Use `--candidate-source llm_chisel_reference` for an endpoint-backed version of
the same flow. The endpoint returns only a validated JSON selection of the
bounded Chisel reference generator; the harness emits RTL locally after that
selection.

For supported tasks, `--candidate-source behavioral` emits deterministic
generated RTL rather than using `--candidate-source reference`. The HOGE INTT
path implements the generated `cuHEpp::TwistINTT<uint32_t,10>` observable
contract:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

This mode is useful when a real arithmetic RTL candidate is needed without the
reference-source evaluator path. Most behavioral generators are functional RTL
for the prepared tests, not optimized Vitis/HLS architectures. The YATA
behavioral generator is the hardware-oriented exception: it emits the checked-in
staged Chisel pipeline as a deterministic structural seed so the behavioral path
can produce Vitis-synthesizable RAINTT RTL.

Current support:

- `hoge_streaming_intt_1024_p64`: correctness-scored HOGE INTT arithmetic.
- `hoge_nttid_1024_identity`: correctness-scored identity smoke path.
- `hoge_streaming_ntt_1024_p64`: standalone NTT wrapper interface/lint gate.
- `hoge_externalproduct_ntt_1024_p64`: correctness-scored HOGE
  ExternalProduct forward-NTT arithmetic.
- `yata_raintt_512_p27`: correctness-scored YATA RAINTT INTT/NTT arithmetic;
  emits the staged structural pipeline RTL for hardware evaluation.

Use `scripts/evaluate_behavioral_candidates.sh` to regenerate and evaluate all
current built-in behavioral candidates with the prepared tests. Add
`--with-vitis` to run the optional host Vivado/Vitis synthesis step after
functional evaluation.

For the hardware-verified YATA behavioral path:

```bash
scripts/autontt_llm_generate.py \
  --task yata_raintt_512_p27 \
  --candidate-source behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 2400
```

The current staged structural seed reports `correct = true`,
`vitis_synthesis_passed = true`, INTT/NTT wait cycles `34`/`35`,
`vitis_lut = 168758`, `vitis_ff = 180141`, and `vitis_dsp = 2296` on the
default U280 target.

## Hardware Goal Loop

Use the runner's hardware goal when the output must be synthesizable RTL rather
than a simulation-oriented behavioral model:

```bash
scripts/autontt_llm_generate.py \
  --task yata_raintt_512_p27 \
  --endpoint lab \
  --goal hardware \
  --attempts 4 \
  --arch-type IDH \
  --modmul-type AUTO \
  --vitis-timeout 3600
```

`--goal hardware` automatically enables Yosys and host Vivado/Vitis synthesis.
It also adds synthesis-specific prompt constraints and writes
`hardware_screen.json` for each attempt. The screen rejects candidates that look
like full-polynomial procedural transform models, which can pass Verilator but
expand into impractical flat arithmetic in Vivado. Final hardware success still
requires `vitis_synthesis_passed = true` and populated `vitis_*` utilization
metrics in `results.json`.

Add `--no-yosys` when the vendor synthesis result is the immediate goal and
Yosys flattening is slower than the Vitis smoke. This does not relax the
hardware success gate; it only skips the optional structural estimate.

If Vivado/Vitis times out or fails, the next attempt receives structured
feedback from the result JSON, Vitis log tail, and extracted DSP-pressure
signals. The intended repair direction is to move toward an AutoNTT-style
iterative, dataflow, or hybrid datapath with bounded butterfly units, pipelined
modular multiplication, and explicit coefficient/twiddle storage.
