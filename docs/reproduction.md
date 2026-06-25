# Reproduction

This page keeps the end-to-end reproduction flow separate from the top-level
README.

## Fresh Clone

From a fresh clone:

```bash
git clone --recurse-submodules https://github.com/virtualsecureplatform/LLM-NTT-Examples.git
cd LLM-NTT-Examples
scripts/reproduce_hls_autontt_metrics.py
```

The wrapper:

- initializes submodules;
- builds or reuses the Apptainer SIF;
- runs generated HLS functional checks;
- runs Vitis HLS synthesis;
- checks that Vitis emitted `syn/verilog` RTL directories;
- writes AutoNTT metric summaries to
  `build/reproduce-hls-autontt/<timestamp>/summary.json` and `report.md`.

By default it runs the small HLS targets plus the full YATA HLS comparison. To
run only one group:

```bash
scripts/reproduce_hls_autontt_metrics.py --targets small
scripts/reproduce_hls_autontt_metrics.py --targets full-yata
```

## Small RTL References

The reduced RTL references are checked in under `variants/small-ntt/rtl` and
can be regenerated deterministically:

```bash
scripts/generate_small_ntt_rtl.py
```

The small YATA references follow the larger RAINTT RTL style: modular
multiplication and butterfly reduction use the dedicated SREDC path instead of
Verilog modulo operators.

They are evaluated through task manifests:

```bash
scripts/evaluate_candidate.sh --task small_hoge32_p64
scripts/evaluate_candidate.sh --task small_yata8_raintt_p27
scripts/evaluate_candidate.sh --task small_yata8x8_raintt_p27
```

Add `--with-vitis` to record AutoNTT-style FPGA metrics. When running inside
Apptainer, bind the host Xilinx install:

```bash
apptainer exec --no-home --pwd /work \
  --bind "$(pwd):/work" \
  --bind /home/opt/xilinx:/home/opt/xilinx \
  llm-ntt-rootless.sif \
  scripts/evaluate_candidate.sh --task small_yata8_raintt_p27 --with-vitis
```

## SIF Selection

`--sif auto` is the default. It uses:

1. `LLM_NTT_SIF`, when set;
2. existing `llm-ntt-rootless.sif`;
3. existing `llm-ntt.sif`;
4. otherwise, builds `llm-ntt.sif` from `apptainer/llm-ntt.def`.

Useful development options:

```bash
scripts/reproduce_hls_autontt_metrics.py --skip-sif-build
scripts/reproduce_hls_autontt_metrics.py --force-sif-build
scripts/reproduce_hls_autontt_metrics.py --sudo-sif-build
```

## Vitis

Vitis remains host-side. The default settings script is:

```text
/home/opt/xilinx/Vitis/2023.2/settings64.sh
```

Override it with:

```bash
scripts/reproduce_hls_autontt_metrics.py \
  --xilinx-root /home/opt/xilinx \
  --vitis-settings Vitis/2023.2/settings64.sh
```

`--vitis-settings` may be absolute or relative to `--xilinx-root`.

## Direct HLS Drivers

Run the small HLS targets directly:

```bash
scripts/run_small_variant_hls_synth_compare.py --variants all --sif auto
```

To skip re-synthesizing the small reference tops during iteration, use the
checked-in small reference baselines:

```bash
scripts/run_small_variant_hls_synth_compare.py \
  --variants all \
  --sif auto \
  --skip-reference-synth
```

Run full YATA directly:

```bash
scripts/run_yata_hls_synth_compare.py --sif auto
```

The small-variant driver writes reference and generated HLS tops, checks both
against TFHEpp-derived references, synthesizes INTT/NTT/combined tops with
Vitis HLS, and compares the resulting `results.json` files with
`scripts/compare_autontt_metrics.py`.

Measured U280 Vitis HLS estimates from a verified run:

| Variant | INTT total cycles | NTT total cycles | LUT | FF | DSP | BRAM | fmax MHz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `hoge32` | 4294 | 4292 | 69693 | 31644 | 40 | 12 | 342.466 |
| `yata8` | 81 | 96 | 17303 | 11938 | 70 | 8 | 342.466 |
| `yata8x8` | 5250 | 9168 | 65492 | 38962 | 156 | 8 | 305.157 |
