# LLM-NTT Examples

This repository packages extracted Number Theoretic Transform RTL variants from
YATA and HOGE with small Verilator tests that compare against the current
TFHEpp C++ reference headers.

## Contents

- `variants/yata-raintt`: YATA compressed 27-bit RAINTT `NTT` and `INTT`.
- `variants/hoge`: merged HOGE Chisel sources for the streaming INTT/NTT
  wrappers, ExternalProduct forward-NTT oracle, and full-vector NTT/INTT
  identity pipeline.
- `third_party/TFHEpp`: TFHEpp submodule used as the C++ reference.
- `docs/ntt-module-specs.md`: top-level module specifications for generating
  replacement Verilog that passes the included tests.
- `tasks/`: machine-readable benchmark task manifests for architecture search.
- `docs/architecture-search-space.md` and `docs/scoring.md`: search knobs and
  evaluation rules.
- `examples/autontt/`: AutoNTT-oriented mapping notes and custom reduction
  examples, including an LLM-based RTL candidate generator.

The copied YATA and HOGE RTL is AGPL-3.0 licensed. See `NOTICE.md` and
`licenses/`.

## Native Run

Install `python3`, `sbt`, `cmake`, `ninja`, `clang++`, and `verilator`, then run:

```bash
git submodule update --init --recursive
scripts/run_all.sh
```

The script generates Verilog with `sbt run`, configures CMake with Clang, builds
the Verilator harnesses, and runs CTest.

## Apptainer Run

Build the container:

```bash
apptainer build --mksquashfs-args "-processors 1" llm-ntt.sif apptainer/llm-ntt.def
```

Run the same build and test flow inside the container:

```bash
apptainer run --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif
```

The `%runscript` expects the repository to be mounted at `/work`. The
single-threaded squashfs argument avoids `mksquashfs` orderer failures observed
on some unprivileged Apptainer hosts.

## Manual Steps

Generate Verilog only:

```bash
scripts/gen_verilog.sh
```

Build and test after Verilog generation:

```bash
cmake -S . -B build -G Ninja -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_C_COMPILER=clang
cmake --build build
ctest --test-dir build --output-on-failure
```

Evaluate a single benchmark task, using the extracted RTL as the baseline:

```bash
scripts/evaluate_candidate.sh --task hoge_streaming_intt_1024_p64
```

Evaluate candidate Verilog in a directory:

```bash
scripts/evaluate_candidate.sh \
  --task hoge_streaming_intt_1024_p64 \
  --verilog-dir candidate/hoge-intt
```

Add an optional flattened Yosys structural estimate:

```bash
scripts/evaluate_candidate.sh \
  --task hoge_externalproduct_ntt_1024_p64 \
  --with-yosys
```

Generate an AutoNTT-style LLM RTL candidate using an OpenAI-compatible endpoint:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_nttid_1024_identity \
  --endpoint lab \
  --strategy behavioral_reference \
  --attempts 1
```

The generator writes prompts, responses, candidate Verilog, and evaluator
results under `build/llm-runs/`. Use `--plan-only` to inspect the AutoNTT-style
search points without calling the LLM, or `--dry-run` to write the prompt only.
`--endpoint lab` reads the private endpoint from `LLM_NTT_LAB_ENDPOINT`; the
endpoint can also be supplied directly with `LLM_NTT_LLM_ENDPOINT`.
The `hoge_nttid_1024_identity` command is only a plumbing smoke test because an
identity implementation can satisfy its observable contract. For real functional
NTT/INTT generation, use a task such as `hoge_streaming_intt_1024_p64`; the
generator rejects trivial pass-through shortcuts for non-identity arithmetic
tasks unless `--allow-shortcuts` is explicitly supplied.

To create a known-good AutoNTT-style run artifact from the extracted RTL, use
the reference candidate source:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source reference \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

This does not count as LLM-generated arithmetic RTL. It copies the task's
golden Verilog into the same run/evaluation layout so functional baselines and
future LLM candidates can be compared with the same prepared tests.

For generated non-reference RTL baselines, use the built-in behavioral
generators:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --candidate-source behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

The HOGE INTT path emits a compact `INTTWrap.v` that implements the same
`cuHEpp::TwistINTT<uint32_t,10>` observable contract and runs through the same
prepared evaluator. Treat these outputs as functional behavioral RTL, not as
optimized AutoNTT/Vitis-quality architectures.

To keep the endpoint in the generation loop without requiring it to emit a
large arithmetic Verilog file verbatim, use the endpoint-guided behavioral
source:

```bash
scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --endpoint lab \
  --candidate-source llm_behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

This mode asks the endpoint for a small JSON selection of a supported
functional generator, validates that selection, emits the corresponding RTL
locally, and evaluates it through the same prepared tests. The private endpoint
is still supplied only through `LLM_NTT_LAB_ENDPOINT`.

Behavioral generation currently supports:

- `hoge_streaming_intt_1024_p64`: correctness-scored HOGE INTT arithmetic.
- `hoge_nttid_1024_identity`: correctness-scored identity smoke path.
- `hoge_streaming_ntt_1024_p64`: standalone NTT wrapper interface/lint gate.
- `hoge_externalproduct_ntt_1024_p64`: correctness-scored HOGE
  ExternalProduct forward-NTT arithmetic.
- `yata_raintt_512_p27`: correctness-scored YATA RAINTT INTT/NTT arithmetic.

Run every built-in behavioral candidate through the prepared evaluator:

```bash
scripts/evaluate_behavioral_candidates.sh
```

Run every endpoint-guided behavioral candidate through the prepared evaluator:

```bash
scripts/evaluate_behavioral_candidates.sh \
  --candidate-source llm_behavioral \
  --endpoint lab
```

Add `--with-vitis` to run the optional host Vivado/Vitis synthesis step after
functional evaluation.

Add an optional host Vivado/Vitis RTL synthesis estimate:

```bash
scripts/evaluate_candidate.sh \
  --task hoge_externalproduct_ntt_1024_p64 \
  --with-vitis
```

The Vitis path synthesizes the task's Verilog top out-of-context with Vivado,
using the AutoNTT-style default target of `xcu280-fsvh2892-2L-e` and a `4.0 ns`
clock. Override these with `--vitis-part`, `--vitis-clock-period`,
`--vitis-clock-port`, `--vitis-jobs`, `--vivado-bin`, or `--xilinx-settings`.
When `/home/opt/xilinx/Vitis/2023.2/settings64.sh` exists, it is sourced by
default before host synthesis.

When only Vitis/Vivado is installed on the host and the other build tools should
come from Apptainer, use the split runner:

```bash
scripts/evaluate_with_apptainer_and_vitis.sh \
  --task hoge_externalproduct_ntt_1024_p64 \
  --with-yosys \
  --sif llm-ntt.sif
```

Refresh all extracted-RTL reference JSON files with host Vitis synthesis:

```bash
scripts/evaluate_baselines_with_vitis.sh --sif llm-ntt.sif
```

## Test Targets

- `yata_raintt_reference_test`: compares streamed YATA `INTT` and `NTT`
  against `raintt::TwistINTT`/`raintt::TwistNTT` with `USE_COMPRESS`. INTT
  input lane `l` at cycle `c` carries coefficient `l * 8 + c`; NTT output lane
  `l` at cycle `c` corresponds to coefficient `l * 8 + c`.
- `hoge_streaming_reference_test`: drives HOGE `INTTWrap` and compares against
  `cuHEpp::TwistINTT`.
- `hoge_externalproduct_ntt_reference_test`: drives HOGE `ExternalProductWrap`
  and compares the final 32-bit torus output against TFHEpp
  `ExternalProduct<lvl1param>`, whose final boundary is `TwistNTT`.
- `hoge_nttid_identity_test`: drives HOGE `NTTid` and checks that the combined
  INTT/NTT pipeline returns the original polynomial modulo `P`.

The HOGE forward `NTTWrap` manifest, `hoge_streaming_ntt_1024_p64`, is a
lint-only tier0 interface task. Use `hoge_externalproduct_ntt_1024_p64` for
HOGE forward NTT arithmetic and latency comparisons.
