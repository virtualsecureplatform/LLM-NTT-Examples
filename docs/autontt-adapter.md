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

## TAPA And Vitis Dependencies

`apptainer/llm-ntt.def` installs the non-Xilinx pieces needed by the AutoNTT
HLS path: `libgflags-dev`, `libgoogle-glog-dev`, OpenCL headers/libraries, and
the PyPI TAPA frontend. It also installs native non-Vitis libraries commonly
needed when building or binding a TAPA/Pasta runtime: Boost
coroutine/context/thread/stacktrace, nlohmann-json, tinyxml2, and yaml-cpp.
Vitis is not installed in the image because it is a licensed Xilinx tool. The
base PyPI `tapa` package also does not include the full TAPA/Pasta C++ runtime
used by AutoNTT C-simulation: `tapa.h`, `libtapa`, and `libfrt`. AutoNTT's
README points to UCLA-VAST TAPA or SFU-HiAccel Pasta and notes testing with
Pasta `0.0.20240104.2`.

Build the image with:

```bash
scripts/build_llm_ntt_sif.sh \
  --with-tapa-runtime \
  --tapa-build-jobs 4 \
  --output llm-ntt-rootless.sif
```

If Apptainer fakeroot is not configured for the current user, use:

```bash
scripts/build_llm_ntt_sif.sh --sudo
```

With `--sudo`, the wrapper stages the SIF under `SIF_TMPDIR`, `TMPDIR`, or
`/tmp`, changes ownership back to the caller, then moves it to `--output`.
Use `--sudo-temp-dir DIR` if `/tmp` is not suitable.
If a future TAPA/Pasta build step needs Vitis during `%post`, add
`--bind-xilinx` or one or more `--build-bind SRC:DST[:OPTS]` options. The bind
makes Vitis visible during build; it does not copy Vitis into the SIF unless the
definition explicitly copies files from the bind.
To build the full RapidStream TAPA runtime into the SIF, use:

```bash
scripts/build_llm_ntt_sif.sh --sudo --with-tapa-runtime --tapa-build-jobs 2
```

That mode downloads Bazelisk, uses Bazel `8.4.2`, clones `rapidstream-tapa`,
patches `VARS.bzl` to use `/home/opt/xilinx` version `2023.2`, builds
`//:tapa-pkg-tar`, and installs the runtime under `/opt/rapidstream-tapa`.
Increase or reduce `--tapa-build-jobs` based on host memory and build pressure;
use `--tapa-bazel-version VERSION` if the TAPA branch requires a different
Bazel release.

After rebuilding the image, check only the image-provided dependencies with:

```bash
apptainer exec --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif \
  scripts/check_autontt_hls_deps.sh --image-only
```

For a full AutoNTT HLS readiness check with the runtime-enabled SIF, bind
Vitis and run the default checker:

```bash
apptainer exec --no-home --pwd /work \
  --bind "$(pwd):/work" \
  --bind /home/opt/xilinx:/home/opt/xilinx \
  llm-ntt-rootless.sif \
  scripts/check_autontt_hls_deps.sh
```

If the full runtime is installed under a different prefix, pass `--tapa-home`
or bind that prefix and set `TAPA_HOME` inside the container.

Then run the generated-HLS compare harness:

```bash
scripts/run_autontt_hls_sif_compare.sh --sif llm-ntt-rootless.sif
```

The harness copies the latest generated HOGE custom HLS artifact into a
timestamped run directory, runs the full dependency check, runs
`make csim_compile`, runs RapidStream `tapa compile`, and writes
`summary.json` plus `report.md` under `build/autontt-hls-sif-compare/`.
The default compare target is the installed U200 platform
`xilinx_u200_gen3x16_xdma_2_202110_1`; pass `--platform` to use another
installed platform.
Use `--tapa-home /path/to/tapa-or-pasta` when the runtime is not installed or
bound under `/opt/pasta`, `/opt/tapa`, or `/opt/rapidstream-tapa`.

## AutoNTT HLS Harness

The checked-in HLS harness invokes the adjacent AutoNTT checkout and captures
the generated HLS artifacts or the environmental blocker:

```bash
scripts/run_autontt_hls_harness.py --modmul-type B
```

That Barrett configuration is a positive control for AutoNTT HLS code
generation. It writes `build/autontt-hls-runs/<timestamp>/summary.json` and
copies the generated `AutoNTT_*` design directory into the run artifacts. The
default architecture filter is `ID`, so the harness asks AutoNTT to try
DataFlow DSE while retaining the iterative fallback. Use `--arch-type D` to
force DataFlow only, or `--arch-type IDH` to include Hybrid as well. The script
auto-selects the default U280 platform when present, otherwise it uses an
installed platform under `/opt/xilinx/platforms`.

For the HOGE `p64` custom reduction files, run:

```bash
scripts/run_autontt_hls_harness.py --modmul-type C
```

The custom path defaults to `--custom-bu-mode estimate`. In that mode the
harness supplies explicit estimated butterfly-unit attributes
`pipeline_depth,dsp,lut,ff = 15,32,2345,1481`, then invokes AutoNTT and captures
the generated HLS design selected from the requested architecture filter, for
example `AutoNTT_I__...` or `AutoNTT_D__...`. These values are only
code-generation estimates; they are not measured synthesis results.

To run AutoNTT's original custom-reduction BU measurement probe, use:

```bash
scripts/run_autontt_hls_harness.py \
  --modmul-type C \
  --custom-bu-mode probe \
  --allow-failure
```

On the current host probe mode reaches AutoNTT's `temp_design` and then fails
before final HLS codegen until the generated C-simulation link line can see
`tapa.h`, `libtapa`, `libfrt`, `glog`, `gflags`, OpenCL, and Vitis HLS
headers. The summary records this as `likely_blocker` and preserves the probed
`temp_design`.

The harness is deliberately separate from `scripts/evaluate_candidate.sh`:
AutoNTT emits a TAPA/Vitis mmap kernel named `NTT_kernel`, while the LLM-NTT
tests consume Verilog task tops such as `INTTWrap`, `ExternalProductWrap`,
`NTTidPackedTop`, and `YataRainttTop`. Passing the prepared tests from the
AutoNTT path still requires TAPA/Vitis HLS-to-RTL synthesis plus a protocol and
ordering adapter.

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

The checked-in workaround is a repository-local HLS generator and synthesis
driver:

```bash
scripts/run_yata_hls_synth_compare.py --sif auto
```

It emits YATA RAINTT HLS into `build/yata-hls-synth-compare/<timestamp>/`,
checks INTT/NTT functional equivalence against TFHEpp, synthesizes the INTT,
NTT, and combined HLS tops with Vitis HLS, writes an evaluator-style
`results.json`, and compares it against
`baselines/extracted-rtl/yata_raintt_512_p27.json` with
`scripts/compare_autontt_metrics.py`. The resource and timing values in this
path are Vitis HLS `csynth` estimates, not post-route RTL implementation
metrics.

## Small Variant HLS

For a fresh-clone end-to-end reproduction of the SIF build, HLS generation,
Vitis HLS RTL emission, functional checks, generated RTL directory checks, and
AutoNTT metric reporting, use:

```bash
scripts/reproduce_hls_autontt_metrics.py
```

This runs the small-variant flow below plus the full YATA HLS comparison unless
`--targets small` or `--targets full-yata` narrows the scope.

Small HLS bring-up targets are available for the requested reduced-size
problems:

- `hoge32`: one radix-32 HOGE p64 butterfly block from the 1024-point NTT decomposition.
- `yata8`: one radix-8 YATA RAINTT block.
- `yata8x8`: 64 YATA coefficients, modeled as 8 lanes by 8 cycles.

Run all three through functional checks, Vitis HLS synthesis, and AutoNTT-style
reference/generated metric comparison:

```bash
scripts/run_small_variant_hls_synth_compare.py --variants all --sif auto
```

The driver emits `reference_*_hls` and `generated_*_hls` tops for INTT, NTT,
and combined transforms or radix blocks under
`build/small-variant-hls-synth-compare/<timestamp>/`. The generated functional
test covers ramp, alternating edge-value, and deterministic pseudo-random
inputs. For `hoge32`, the oracle is the exposed TFHEpp radix butterfly itself,
without final twist/modswitch, because this target is one radix stage of the
full 1024-point decomposition.

Measured U280 Vitis HLS estimates from a verified run:

| Variant | INTT total cycles | NTT total cycles | LUT | FF | DSP | BRAM | fmax MHz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `yata8` | 81 | 96 | 17303 | 11938 | 70 | 8 | 342.466 |
| `yata8x8` | 5250 | 9168 | 65492 | 38962 | 156 | 8 | 305.157 |

The previous `hoge32` HLS numbers were for an obsolete standalone 32-point
transform. Regenerate them before comparing the current radix-32 block.

Longer-term direct AutoNTT extensions would still be:

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
when using a different server. In this workspace, `--endpoint kunashiri`
resolves to the llama.cpp OpenAI-compatible server at
`http://kunashiri:8080/v1`; use `--disable-thinking` for Qwen-style models that
otherwise return reasoning content before the requested JSON.
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

YATA additionally supports source-level pipeline exploration:

```bash
scripts/autontt_llm_generate.py \
  --task yata_raintt_512_p27 \
  --candidate-source chisel_pipeline \
  --arch-type D \
  --modmul-type C \
  --pipeline-profiles AUTO \
  --target-frequency-mhz 300 \
  --goal hardware \
  --no-yosys \
  --attempts 3 \
  --vitis-timeout 1800
```

The generated search points carry exact multiplier and signed-reduction stage
counts. At 300 MHz, `AUTO` tries the reduction-split `f300` profile first, then
`deep`, then the original `baseline`. Correctness remains a hard gate, and the
hardware goal also requires `vitis_fmax_mhz >= 300` and nonnegative
`vitis_timing_wns_ns`. The run-level `dse_summary.json` retains every evaluated
profile and its correctness, latency, utilization, and timing metrics.

The verified U280 post-synthesis result for `f300` is 169580 LUT, 201388 FF,
2296 DSP, 0 BRAM/URAM, 40/41 INTT/NTT wait cycles, `+0.682 ns` WNS at
3.333 ns, and a 2.651 ns achieved period (`377.17 MHz` estimated fmax). The
checked-in baseline is 34/35 cycles and `215.38 MHz`; both designs preserve
eight-cycle input and output bursts.

Use `--candidate-source llm_chisel_reference` for an endpoint-backed version of
the same flow. The endpoint returns only a validated JSON selection of the
bounded Chisel reference generator; the harness emits RTL locally after that
selection.

For supported tasks, `--candidate-source behavioral` emits deterministic
generated RTL rather than using `--candidate-source reference`. The built-in
HOGE arithmetic and YATA behavioral generators seed from checked-in staged
Chisel pipeline RTL so the generated-candidate path can be used for hardware
evaluation:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

This mode is useful when a synthesizable arithmetic RTL candidate is needed
without the `--candidate-source reference` evaluator path. HOGE identity is a
compact smoke RTL because that task's observable contract is identity, not a
standalone NTT. These are deterministic synthesizable seeds, not novel
endpoint-designed architectures.

Current support:

- `hoge_streaming_intt_1024_p64`: correctness-scored HOGE INTT arithmetic;
  emits the staged structural `INTTWrap` pipeline RTL.
- `hoge_nttid_1024_identity`: correctness-scored identity smoke path; emits a
  compact synthesizable `NTTidPackedTop` identity RTL.
- `hoge_streaming_ntt_1024_p64`: standalone NTT wrapper interface/lint gate;
  emits the staged structural `NTTWrap` pipeline RTL.
- `hoge_externalproduct_ntt_1024_p64`: correctness-scored HOGE
  ExternalProduct forward-NTT arithmetic; emits the staged structural
  `ExternalProductWrap` RTL.
- `yata_raintt_512_p27`: correctness-scored YATA RAINTT INTT/NTT arithmetic;
  emits the staged structural pipeline RTL for hardware evaluation.

Use `scripts/evaluate_behavioral_candidates.sh` to regenerate and evaluate all
current built-in behavioral candidates with the prepared tests. Add
`--with-vitis` to run the optional host Vivado/Vitis synthesis step after
functional evaluation.

For the local endpoint-backed harness defaults, run:

```bash
scripts/run_autontt_kunashiri_harness.sh
```

This delegates to the behavioral-candidate evaluator with
`--candidate-source llm_behavioral`, `--endpoint kunashiri`,
`--disable-thinking`, Apptainer evaluation, and a dedicated output root under
`build/autontt-kunashiri-harness/`. It also writes an aggregate
`build/autontt-kunashiri-harness/summary.json` result for automated checks.

For HOGE, use the bundle runner when the intent is to test one generated RTL
candidate across all HOGE task boundaries instead of generating separate-looking
candidate directories per task:

```bash
scripts/evaluate_hoge_bundle.py \
  --candidate-source llm_behavioral \
  --endpoint kunashiri \
  --disable-thinking \
  --sif auto \
```

The endpoint selects the bounded `hoge_behavioral_bundle` generator once. The
harness then writes one candidate directory containing `INTTWrap.v`,
`ExternalProductWrap.v`, `NTTWrap.v`, and `NTTidPackedTop.v`; every selected
HOGE task oracle reads from that same directory via `--verilog-dir`.

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
default U280 target. The generated body matches the checked-in Chisel reference
after removing generated header comments, so the AutoNTT latency and resource
ratios against that reference are `1.0`.

Hardware-verified HOGE behavioral commands:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --endpoint lab \
  --candidate-source llm_behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 1800 \
  --output-root build/lab-llm-behavioral-intt-hardware \
  --sif auto \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}'

scripts/evaluate_hoge_bundle.py \
  --candidate-source llm_behavioral \
  --endpoint lab \
  --task hoge_nttid_1024_identity \
  --with-vitis \
  --vitis-timeout 600 \
  --output-root build/lab-hoge-bundle-identity-hardware \
  --sif auto \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}'
```

The lower-level non-endpoint reproduction commands remain useful for checking
individual tops:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 2400 \
  --output-root build/behavioral-hoge-structural-hardware \
  --sif auto

scripts/autontt_llm_generate.py \
  --task hoge_externalproduct_ntt_1024_p64 \
  --candidate-source behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 2400 \
  --output-root build/behavioral-hoge-structural-hardware \
  --sif auto

scripts/autontt_llm_generate.py \
  --task hoge_streaming_ntt_1024_p64 \
  --candidate-source behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 1800 \
  --output-root build/behavioral-hoge-structural-hardware \
  --sif auto

scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --candidate-source behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 600 \
  --output-root build/behavioral-identity-compact-hardware \
  --sif auto
```

Measured HOGE U280 metrics:

| Task | Correct | Vitis | Latency metric | LUT | FF | DSP | BRAM | URAM | WNS ns | fmax MHz |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `hoge_streaming_intt_1024_p64` | true | true | total 129 cycles, wait 65 | 140242 | 239475 | 512 | 0 | 0 | 1.518 | 402.901 |
| `hoge_externalproduct_ntt_1024_p64` | true | true | total 480 cycles, wait 320 | 325773 | 522113 | 2048 | 71.5 | 0 | 1.781 | 450.653 |
| `hoge_streaming_ntt_1024_p64` | lint-only | true | interface gate only | 90300 | 194109 | 512 | 0 | 0 | 1.519 | 403.063 |
| `hoge_nttid_1024_identity` | true | true | identity smoke, wait 33 | 0 | 0 | 0 | 0 | 0 | no timed path | unavailable |

The generated bodies for HOGE INTT, ExternalProduct, and NTT interface match
the checked-in Chisel reference RTL after removing generated header comments.
Those completed arithmetic/interface hardware runs therefore score `1.0`
against that reference under the documented latency/resource ratio formula. The
identity smoke path is functionally correct and Vitis-synthesizable, but it
should be reported outside the NTT arithmetic-ranked set.

To compare a generated HOGE bundle result against a freshly synthesized
reference result, evaluate both sides with the same task, part, and clock, then
run the metric comparator:

```bash
export LLM_NTT_SIF="/path/to/llm-ntt.sif"

scripts/evaluate_with_apptainer_and_vitis.sh \
  --task hoge_streaming_intt_1024_p64 \
  --build-dir build/autontt-compare/hoge-intt-reference \
  --results build/autontt-compare/hoge-intt-reference/results.json \
  --sif "${LLM_NTT_SIF}" \
  --vitis-timeout 1800

scripts/evaluate_hoge_bundle.py \
  --candidate-source llm_behavioral \
  --endpoint lab \
  --task hoge_streaming_intt_1024_p64 \
  --with-vitis \
  --vitis-timeout 1800 \
  --sif auto \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --output-root build/lab-hoge-bundle-intt-hardware

run_dir="$(ls -td build/lab-hoge-bundle-intt-hardware/* | head -n1)"

scripts/compare_autontt_metrics.py \
  --reference build/autontt-compare/hoge-intt-reference/results.json \
  --candidate "${run_dir}/eval/hoge_streaming_intt_1024_p64/results.json" \
  --output build/autontt-compare/hoge-intt-comparison.json
```

`scripts/compare_autontt_metrics.py` writes a comparison JSON with the
AutoNTT-style latency score, resource ratios, weighted resource penalty,
resource-aware score, and timing deltas. Missing synthesis metrics stay
unavailable rather than being silently filled from stale baseline files.

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
metrics in `results.json`. When the task or command defines a target frequency,
it also requires the reported fmax to meet that target with nonnegative WNS.
The per-attempt decision and individual checks are in `hardware_goal.json`.

Add `--no-yosys` when the vendor synthesis result is the immediate goal and
Yosys flattening is slower than the Vitis smoke. This does not relax the
hardware success gate; it only skips the optional structural estimate.

If Vivado/Vitis times out or fails, the next attempt receives structured
feedback from the result JSON, Vitis log tail, and extracted DSP-pressure
signals. The intended repair direction is to move toward an AutoNTT-style
iterative, dataflow, or hybrid datapath with bounded butterfly units, pipelined
modular multiplication, and explicit coefficient/twiddle storage.
