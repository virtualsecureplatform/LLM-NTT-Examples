# LLM-NTT Examples

This repository packages extracted Number Theoretic Transform RTL variants from
YATA and HOGE with small Verilator tests that compare against the current
TFHEpp C++ reference headers.

## Contents

- `variants/yata-raintt`: YATA compressed 27-bit RAINTT `NTT` and `INTT`.
- `variants/hoge-streaming`: HOGE streaming 64-bit INTT plus an NTT wrapper.
- `variants/hoge-externalproduct`: HOGE ExternalProduct pipeline used as the
  executable forward NTT oracle.
- `variants/hoge-nttid`: HOGE full-vector NTT/INTT identity pipeline.
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
  --task hoge_streaming_intt_1024_p64 \
  --endpoint http://<openai-compatible-endpoint>/v1 \
  --attempts 1
```

The generator writes prompts, responses, candidate Verilog, and evaluator
results under `build/llm-runs/`. Use `--plan-only` to inspect the AutoNTT-style
search points without calling the LLM, or `--dry-run` to write the prompt only.
The endpoint can also be supplied with `LLM_NTT_LLM_ENDPOINT`.

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
