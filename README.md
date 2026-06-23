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
scripts/build_llm_ntt_sif.sh
```

Run the same build and test flow inside the container:

```bash
apptainer run --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif
```

The `%runscript` expects the repository to be mounted at `/work`. The
single-threaded squashfs argument avoids `mksquashfs` orderer failures observed
on some unprivileged Apptainer hosts.

The image also carries the non-Xilinx dependencies used by the AutoNTT HLS
path: `libgflags-dev`, `libgoogle-glog-dev`, OpenCL headers/libraries, and the
Python TAPA frontend. It also installs the native non-Vitis headers/libraries
commonly needed by TAPA/Pasta runtime builds: Boost
coroutine/context/thread/stacktrace, nlohmann-json, tinyxml2, and yaml-cpp.
Vitis remains a host-side licensed tool, and the base PyPI `tapa` package does
not provide the full TAPA/Pasta C++ runtime (`tapa.h`, `libtapa`, `libfrt`)
needed by AutoNTT's generated C-simulation link line.

For the rootless image with the full RapidStream TAPA runtime installed, build
with:

```bash
scripts/build_llm_ntt_sif.sh \
  --with-tapa-runtime \
  --tapa-build-jobs 4 \
  --output llm-ntt-rootless.sif
```

If your Apptainer installation cannot use fakeroot, build with:

```bash
scripts/build_llm_ntt_sif.sh --sudo
```

With `--sudo`, the wrapper stages the SIF under `SIF_TMPDIR`, `TMPDIR`, or
`/tmp`, changes ownership back to the caller, then moves it to `--output`
inside the repository. Use `--sudo-temp-dir DIR` if `/tmp` is not suitable.
Use `--bind-xilinx` when a build-time `%post` step needs the host Xilinx tree;
this bind is read-only and does not copy Vitis into the image.
To build and install the full RapidStream TAPA runtime inside a sudo-built
image, bind the host Xilinx tree and enable the opt-in runtime build:

```bash
scripts/build_llm_ntt_sif.sh --sudo --with-tapa-runtime --tapa-build-jobs 2
```

This downloads Bazelisk, uses Bazel `8.4.2`, clones `rapidstream-tapa`, patches
its `VARS.bzl` to use `/home/opt/xilinx` version `2023.2`, builds
`//:tapa-pkg-tar`, and installs `tapacc`, `tapa.h`, `libtapa`, and `libfrt`
under `/opt/rapidstream-tapa` in the SIF. It can take a long time and needs the
build-time Vitis bind. Use `--tapa-bazel-version VERSION` if the TAPA branch
requires a different Bazel release.

For an image-only sanity check after rebuilding:

```bash
apptainer exec --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif \
  scripts/check_autontt_hls_deps.sh --image-only
```

For full AutoNTT HLS C-simulation/synthesis checks with the runtime-enabled
SIF, bind the host Xilinx tree, then run the default checker:

```bash
apptainer exec --no-home --pwd /work \
  --bind "$(pwd):/work" \
  --bind /home/opt/xilinx:/home/opt/xilinx \
  llm-ntt-rootless.sif \
  scripts/check_autontt_hls_deps.sh
```

After the SIF and host Vitis tree are visible, run the generated HLS
compile/synthesis comparison harness. The default platform is the installed
U200 platform `xilinx_u200_gen3x16_xdma_2_202110_1`; pass `--platform` to
target another installed platform:

```bash
scripts/run_autontt_hls_sif_compare.sh --sif llm-ntt-rootless.sif
```

It copies the latest generated HOGE custom AutoNTT HLS artifact, runs the full
dependency check inside the SIF, runs `make csim_compile`, runs
RapidStream `tapa compile`, and writes a timestamped `summary.json` and
`report.md` under `build/autontt-hls-sif-compare/`.

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
endpoint can also be supplied directly with `LLM_NTT_LLM_ENDPOINT`. In this
workspace, `--endpoint kunashiri` resolves to the llama.cpp OpenAI-compatible
server at `http://kunashiri:8080/v1`; pass `--disable-thinking` for Qwen-style
models that otherwise return `reasoning_content` before the requested JSON.
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
  --endpoint kunashiri \
  --disable-thinking \
  --candidate-source llm_behavioral \
  --strategy hardware \
  --arch-type I \
  --modmul-type C
```

This mode asks the endpoint for a small JSON selection of a supported
functional generator, validates that selection, emits the corresponding RTL
locally, and evaluates it through the same prepared tests. The private endpoint
is still supplied only through `LLM_NTT_LAB_ENDPOINT`.

For the local `kunashiri` llama.cpp server, the full endpoint-backed functional
harness can be run with one command:

```bash
scripts/run_autontt_kunashiri_harness.sh
```

By default this writes artifacts to `build/autontt-kunashiri-harness/`, asks
`kunashiri` to select each bounded RTL generator, emits the selected candidate
RTL locally, and runs the prepared LLM-NTT tests through Apptainer. The
aggregate pass/fail record is written to
`build/autontt-kunashiri-harness/summary.json`. Add `--task <task-id>` to run a
single task or `--with-vitis --vitis-timeout SEC` for optional Vivado/Vitis
synthesis.

To try the adjacent AutoNTT HLS backend directly, use the HLS harness:

```bash
scripts/run_autontt_hls_harness.py --modmul-type B
```

This runs `../AutoNTT/automation_framework/AutoNTT.py`, captures generated
TAPA/Vitis HLS artifacts under `build/autontt-hls-runs/<timestamp>/`, and
writes `summary.json`. The Barrett path is a positive code-generation control.
To generate HOGE `p64` custom-reduction HLS source, run:

```bash
scripts/run_autontt_hls_harness.py --modmul-type C
```

For custom reductions the harness defaults to `--custom-bu-mode estimate`,
which supplies explicit estimated butterfly-unit attributes
`pipeline_depth,dsp,lut,ff = 15,32,2345,1481` to unblock AutoNTT source
generation. The generated HLS source is useful for adapter work, but those BU
attributes are not measured synthesis results. To run AutoNTT's original
C-sim/TAPA/Autobridge custom-BU measurement probe, use:

```bash
scripts/run_autontt_hls_harness.py \
  --modmul-type C \
  --custom-bu-mode probe \
  --allow-failure
```

On this host the measured probe reaches AutoNTT's `temp_design` and is blocked
until the generated C-simulation link line can see `tapa.h`, `libtapa`,
`libfrt`, `glog`, `gflags`, OpenCL, and Vitis HLS headers. Use
`scripts/check_autontt_hls_deps.sh` to distinguish the rebuilt image's
non-Xilinx dependencies from the full TAPA/Pasta/Vitis runtime needed for
synthesis. AutoNTT HLS artifacts are not yet Verilog candidates for the
prepared tests; passing this repository's task manifests from that path still
requires HLS-to-RTL synthesis plus an interface/order adapter for task tops such
as `INTTWrap` and `ExternalProductWrap`.

YATA is not a direct AutoNTT backend input because the extracted task is
`N = 512`. To generate an LLM-style YATA HLS candidate, test it against TFHEpp,
synthesize it with Vitis HLS, and compare its HLS estimates against the
extracted RTL reference using the AutoNTT metric script, run:

```bash
scripts/run_yata_hls_synth_compare.py --sif auto
```

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
  --endpoint kunashiri \
  --disable-thinking
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
