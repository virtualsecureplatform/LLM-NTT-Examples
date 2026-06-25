# LLM-NTT Examples

This repository packages extracted Number Theoretic Transform RTL variants from
YATA and HOGE, plus harnesses for functional checking, HLS generation, and
AutoNTT-style metric comparison.

## Contents

- `variants/yata-raintt`: YATA compressed 27-bit RAINTT `NTT` and `INTT`.
- `variants/hoge`: HOGE Chisel sources for streaming INTT/NTT wrappers,
  ExternalProduct forward-NTT, and the full-vector identity pipeline.
- `variants/small-ntt/rtl`: generated small HOGE/YATA RTL references used by
  the reduced AutoNTT comparison tasks.
- `third_party/TFHEpp`: TFHEpp submodule used as the C++ reference.
- `tasks/`: benchmark task manifests.
- `scripts/`: native, Apptainer, HLS, and metric comparison entry points.
- `docs/`: architecture notes, scoring rules, Apptainer setup, and
  reproducibility flows.
- `examples/autontt/`: AutoNTT-oriented mapping notes and LLM candidate
  generation.

The copied YATA and HOGE RTL is AGPL-3.0 licensed. See `NOTICE.md` and
`licenses/`.

## Quick Start

Run the native Verilator checks:

```bash
git submodule update --init --recursive
scripts/run_all.sh
```

Run the fresh-clone HLS reproduction flow:

```bash
scripts/reproduce_hls_autontt_metrics.py
```

That wrapper builds or reuses the Apptainer SIF, runs HLS functional and Vitis
HLS synthesis checks, verifies generated RTL directories, and writes
`build/reproduce-hls-autontt/<timestamp>/report.md`.

## Common Commands

Build the default Apptainer image:

```bash
scripts/build_llm_ntt_sif.sh
```

Run native build/test inside the image:

```bash
apptainer run --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif
```

Evaluate one RTL task:

```bash
scripts/evaluate_candidate.sh --task hoge_streaming_intt_1024_p64
```

Regenerate the small RTL references:

```bash
scripts/generate_small_ntt_rtl.py
```

Generate an AutoNTT-style LLM candidate:

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

Run the small HLS comparison targets directly:

```bash
scripts/run_small_variant_hls_synth_compare.py --variants all --sif auto
```

Run the full YATA HLS comparison directly:

```bash
scripts/run_yata_hls_synth_compare.py --sif auto
```

## More Detail

- `docs/reproduction.md`: fresh-clone HLS reproduction and expected outputs.
- `docs/apptainer.md`: SIF build modes, Vitis binding, and TAPA runtime notes.
- `docs/autontt-adapter.md`: AutoNTT adapter boundary and HLS bring-up details.
- `examples/autontt/README.md`: LLM generator and AutoNTT examples.
- `docs/scoring.md`: correctness and metric scoring rules.

## Test Targets

- `yata_raintt_reference_test`: streamed YATA `INTT`/`NTT` against
  `raintt::TwistINTT`/`raintt::TwistNTT`.
- `hoge_streaming_reference_test`: HOGE `INTTWrap` against
  `cuHEpp::TwistINTT`.
- `hoge_externalproduct_ntt_reference_test`: HOGE `ExternalProductWrap`
  against TFHEpp `ExternalProduct<lvl1param>`.
- `hoge_nttid_identity_test`: HOGE `NTTid` identity pipeline.
- `small_hoge32_reference_test`: generated HOGE radix-32 butterfly RTL against
  TFHEpp/cuHEpp.
- `small_yata8_reference_test` and `small_yata8x8_reference_test`: generated
  YATA RAINTT RTL against TFHEpp `raintt`.

The HOGE forward `NTTWrap` manifest, `hoge_streaming_ntt_1024_p64`, is a
lint-only tier0 interface task. Use `hoge_externalproduct_ntt_1024_p64` for
HOGE forward NTT arithmetic and latency comparisons.
