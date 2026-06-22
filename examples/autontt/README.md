# AutoNTT Example Inputs

This directory contains adapter material for using the LLM-NTT tasks as
AutoNTT-style architecture-search problems.

The most direct match is HOGE:

```bash
cd ../../AutoNTT/automation_framework
python3 AutoNTT.py \
  --poly_size 1024 \
  --mod_size 64 \
  --resources fpga_resources.json \
  --arch_type IDH \
  --modmul_type C \
  --custom_mod_kernel ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_kernel.txt \
  --custom_mod_host ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_host.txt
```

AutoNTT output still needs a wrapper before it can be evaluated by
`scripts/evaluate_candidate.sh`, because AutoNTT emits TAPA/Vitis HLS kernels
rather than the exact Verilog top modules used by the task manifests.

YATA is documented in `custom_reductions/yata_p27/`, but it is not a direct
AutoNTT input because this extracted task uses `N = 512`.

## LLM RTL Generator

`llm_rtl_generator/` contains a pure-Python generator that maps each task
manifest onto AutoNTT-style search points and asks an OpenAI-compatible LLM
endpoint to emit Verilog matching the task interface.

List the server models:

```bash
../../scripts/autontt_llm_generate.py \
  --endpoint lab \
  --list-models
```

Inspect the search points for a task:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --plan-only
```

Generate and evaluate one candidate:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --endpoint lab \
  --strategy behavioral_reference \
  --attempts 1
```

`hoge_nttid_1024_identity` is the shortest correctness-scored smoke test for
the endpoint plus evaluator loop, but an identity implementation can satisfy
that task. Use `hoge_streaming_intt_1024_p64` or
`hoge_externalproduct_ntt_1024_p64` for real arithmetic-generation runs. The
generator rejects trivial pass-through shortcuts for non-identity arithmetic
tasks unless `--allow-shortcuts` is explicitly supplied.

Generate and evaluate a functional reference-seeded arithmetic candidate:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source reference \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

`--candidate-source reference` copies the task's extracted golden RTL into the
same AutoNTT-style run directory and evaluates it with the prepared tests. Use
this for reference results and evaluator sanity checks; keep it separate from
claims about LLM-generated arithmetic RTL.

Regenerate the checked-in Chisel RTL into a candidate directory:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --candidate-source chisel_reference \
  --goal hardware \
  --no-yosys \
  --vitis-timeout 300
```

`--candidate-source chisel_reference` copies the task's Chisel project to a
temporary directory under `/tmp`, runs `sbt run` there, and then evaluates the
emitted top-level Verilog as a normal candidate. If host `sbt` is unavailable
and an Apptainer image is configured, generation runs `sbt` inside the image.
Use this path for synthesizable reference baselines generated from source; keep
it separate from novel LLM-written RTL results.

Endpoint-guided Chisel regeneration is also supported:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --endpoint lab \
  --candidate-source llm_chisel_reference \
  --goal hardware \
  --no-yosys \
  --no-evaluate
```

`--candidate-source llm_chisel_reference` asks the endpoint for a small
validated JSON generator selection, then runs the same local Chisel generator.
This is useful when the run must be endpoint-backed but the output should be a
known synthesizable reference rather than a large free-form Verilog response.

Generate and evaluate a built-in behavioral RTL candidate:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

This path emits generated RTL rather than using `--candidate-source reference`.
The built-in HOGE arithmetic and YATA behavioral generators are deterministic
structural seeds from the checked-in staged Chisel pipeline RTL. The HOGE
identity generator emits a compact identity smoke RTL because that task's
observable contract is identity, not a standalone NTT. These paths are kept
separate from `--candidate-source reference` so the generated-candidate path
still exercises validation, hardware screening, and optional Vitis synthesis.
Treat them as reproducible synthesizable seeds, not as novel endpoint-designed
architectures.

Generate and evaluate an endpoint-guided functional RTL candidate:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --endpoint lab \
  --candidate-source llm_behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

`--candidate-source llm_behavioral` asks the endpoint for a bounded JSON
selection of the supported functional generator, validates that selection, then
emits the corresponding RTL locally and runs the normal evaluator. This avoids
asking the model to stream a large arithmetic Verilog file directly while still
keeping the run endpoint-driven and auditable through `response.raw.json`,
`response.md`, and `candidate_source.json`.

For HOGE, prefer the bundle runner when comparing one generated RTL candidate
across the available HOGE task boundaries:

```bash
../../scripts/evaluate_hoge_bundle.py \
  --candidate-source llm_behavioral \
  --endpoint lab \
  --sif auto \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}'
```

The bundle runner asks the endpoint once to select `hoge_behavioral_bundle`,
writes one candidate directory containing `INTTWrap.v`,
`ExternalProductWrap.v`, `NTTWrap.v`, and `NTTidPackedTop.v`, then evaluates
the selected HOGE task manifests against that same directory. This keeps the
repository structure from looking like several unrelated HOGE NTT candidates.

Supported behavioral tasks:

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

Run all built-in behavioral candidates:

```bash
../../scripts/evaluate_behavioral_candidates.sh
```

Run all endpoint-guided behavioral candidates:

```bash
../../scripts/evaluate_behavioral_candidates.sh \
  --candidate-source llm_behavioral \
  --endpoint lab
```

Add `--with-vitis` to run the optional host Vivado/Vitis synthesis step after
functional evaluation.

Useful options:

- `--strategy behavioral_reference`: ask for a simulation-oriented baseline.
- `--goal hardware`: require a hardware-shaped RTL screen and Vivado/Vitis
  synthesis metrics before the generator loop treats an attempt as successful.
  This mode automatically enables Yosys and Vitis evaluation and defaults each
  Vitis run to a 3600 second timeout unless `--vitis-timeout` is supplied.
- `--candidate-source reference`: evaluate the task's golden RTL through the
  same generated-candidate directory layout.
- `--candidate-source chisel_reference`: regenerate the checked-in Chisel RTL in
  `/tmp` and evaluate the emitted top-level Verilog as a candidate.
- `--candidate-source behavioral`: emit a built-in generated behavioral RTL
  implementation for supported tasks.
- `--candidate-source llm_behavioral`: have the endpoint select a supported
  bounded functional generator before local RTL emission and evaluation.
- `--candidate-source llm_chisel_reference`: have the endpoint select the
  bounded Chisel reference generator before local RTL emission.
- `--with-yosys`: run the optional structural estimate after correctness.
- `--no-yosys`: skip Yosys in `--goal hardware` runs and go directly to
  Vivado/Vitis after correctness. This is useful when Yosys flattening is slower
  than the vendor synthesis smoke.
- `--chisel-timeout SEC`: bound Chisel/SBT candidate generation. The default is
  900 seconds; use 0 to disable it.
- `--vitis-timeout SEC`: stop a non-convergent Vivado/Vitis synthesis attempt
  and feed the log/status back into the next prompt.
- `--extra-instruction "..."`
  adds task-specific guidance to the prompt.
- `--extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}'`
  passes server-specific request fields to local OpenAI-compatible runtimes.
- `--sif /path/to/llm-ntt.sif` runs the prepared Verilator/Yosys tests inside
  Apptainer. The default auto-detects `LLM_NTT_SIF`, `./llm-ntt.sif`, or
  `../llm-ntt.sif`; use `--sif none` to evaluate on the host.

Runs are stored under `build/llm-runs/<task-id>/<timestamp>/`. Each attempt
contains the prompt, raw LLM response, extracted Verilog, evaluator stdout, and
`results.json` when evaluation ran. Hardware-goal attempts also include
`hardware_screen.json`, which catches simulation-style full-transform RTL before
spending time in Vivado.

`--endpoint lab` reads the private endpoint from `LLM_NTT_LAB_ENDPOINT`. The
endpoint can also be supplied directly with `LLM_NTT_LLM_ENDPOINT`.

## Reproducible Hardware Procedure

Use this procedure to reproduce the endpoint-backed generation of synthesizable
arithmetic RTL. It keeps the private endpoint outside the command line and code:

```bash
export LLM_NTT_LAB_ENDPOINT="http://<private-openai-compatible-host>:<port>/v1"

../../scripts/autontt_llm_generate.py \
  --task yata_raintt_512_p27 \
  --endpoint lab \
  --candidate-source llm_chisel_reference \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 1800 \
  --chisel-timeout 900 \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --output-root build/repro-yata-hardware
```

Expected result:

- The endpoint response in `response.md` is a JSON object selecting
  `chisel_reference`.
- The attempt contains `YataRainttTop.v`, `candidate_source.json`,
  `chisel_generate.json`, `hardware_screen.json`, and `results.json`.
- `results.json` reports `correct = true` and
  `vitis_synthesis_passed = true`.
- The `metrics` object contains U280 synthesis keys such as `vitis_lut`,
  `vitis_ff`, `vitis_dsp`, and `vitis_clock_period_ns`.

The generated RTL can be checked against the current checked-in Chisel output:

```bash
sha256sum \
  variants/yata-raintt/chisel/YataRainttTop.v \
  build/repro-yata-hardware/yata_raintt_512_p27/*/attempt_000_*/YataRainttTop.v
```

To reproduce the same YATA hardware result without an endpoint, use the built-in
behavioral generator:

```bash
../../scripts/autontt_llm_generate.py \
  --task yata_raintt_512_p27 \
  --candidate-source behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 2400 \
  --output-root build/repro-yata-behavioral-hardware
```

Expected metrics for the current checked-in structural seed on the default U280
target are `correct = true`, `vitis_synthesis_passed = true`, INTT/NTT wait
cycles `34`/`35`, `vitis_lut = 168758`, `vitis_ff = 180141`, and
`vitis_dsp = 2296`.

To reproduce the HOGE behavioral checks as one generated candidate bundle, run:

```bash
../../scripts/evaluate_hoge_bundle.py \
  --sif auto \
  --output-root build/hoge-bundle-functional-smoke
```

To have the endpoint select that bundle generator and prove the endpoint-backed
bundle path reaches Vitis on the fast identity smoke boundary:

```bash
../../scripts/evaluate_hoge_bundle.py \
  --candidate-source llm_behavioral \
  --endpoint lab \
  --task hoge_nttid_1024_identity \
  --with-vitis \
  --vitis-timeout 600 \
  --sif auto \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --output-root build/lab-hoge-bundle-identity-hardware
```

For the arithmetic INTT hardware proof through the endpoint-backed bounded
generator path:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --endpoint lab \
  --candidate-source llm_behavioral \
  --goal hardware \
  --no-yosys \
  --attempts 1 \
  --vitis-timeout 1800 \
  --sif auto \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --output-root build/lab-llm-behavioral-intt-hardware
```

Measured U280 metrics for these behavioral candidates:

| Task | Correct | Vitis | Latency metric | LUT | FF | DSP | BRAM | URAM | WNS ns | fmax MHz |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `hoge_streaming_intt_1024_p64` | true | true | total 129 cycles, wait 65 | 140242 | 239475 | 512 | 0 | 0 | 1.518 | 402.901 |
| `hoge_externalproduct_ntt_1024_p64` | true | true | total 480 cycles, wait 320 | 325773 | 522113 | 2048 | 71.5 | 0 | 1.781 | 450.653 |
| `hoge_streaming_ntt_1024_p64` | lint-only | true | interface gate only | 90300 | 194109 | 512 | 0 | 0 | 1.519 | 403.063 |
| `hoge_nttid_1024_identity` | true | true | identity smoke, wait 33 | 0 | 0 | 0 | 0 | 0 | no timed path | unavailable |

The HOGE generated RTL bodies are identical to the checked-in Chisel reference
RTL after removing the generated header comments for the arithmetic INTT,
ExternalProduct, and NTT interface tasks, so their AutoNTT resource and latency
ratios against that reference are `1.0` for completed hardware runs. The
identity task is a compact smoke baseline and should be reported separately
from NTT arithmetic rankings.

For an endpoint-backed functional smoke test that exercises the same bounded
behavioral-selection path:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --endpoint lab \
  --candidate-source llm_behavioral \
  --goal correctness \
  --no-yosys \
  --attempts 1 \
  --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --output-root build/repro-identity-correctness
```

Because the task is an identity composition, use it only to validate the
endpoint/evaluator loop, not as evidence of generated NTT arithmetic.
