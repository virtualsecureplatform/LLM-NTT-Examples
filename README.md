# LLM-NTT Examples

This repository packages extracted Number Theoretic Transform RTL variants from
YATA and HOGE with small Verilator tests that compare against the current
TFHEpp C++ reference headers.

## Contents

- `variants/yata-raintt`: YATA compressed 27-bit RAINTT `NTT` and `INTT`.
- `variants/hoge-streaming`: HOGE streaming 64-bit INTT plus an NTT wrapper.
- `variants/hoge-nttid`: HOGE full-vector NTT/INTT identity pipeline.
- `third_party/TFHEpp`: TFHEpp submodule used as the C++ reference.
- `docs/ntt-module-specs.md`: top-level module specifications for generating
  replacement Verilog that passes the included tests.

The copied YATA and HOGE RTL is AGPL-3.0 licensed. See `NOTICE.md` and
`licenses/`.

## Native Run

Install `sbt`, `cmake`, `ninja`, `clang++`, and `verilator`, then run:

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

## Test Targets

- `yata_raintt_reference_test`: drives streamed YATA `INTT` as a valid-output
  smoke test and compares streamed YATA `NTT` against `raintt::TwistNTT` with
  `USE_COMPRESS`. The standalone YATA `NTT` emits eight cycles in transposed
  lane order: output lane `l` at cycle `c` corresponds to coefficient
  `l * 8 + c`.
- `hoge_streaming_reference_test`: drives HOGE `INTTWrap` and compares against
  `cuHEpp::TwistINTT`.
- `hoge_nttid_identity_test`: drives HOGE `NTTid` and checks that the combined
  INTT/NTT pipeline returns the original polynomial modulo `P`.
