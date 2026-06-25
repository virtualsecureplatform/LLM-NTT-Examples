# Extracted RTL Baselines

These JSON files were generated with `scripts/evaluate_candidate.sh` using the
checked-in extracted RTL.

They provide reference correctness and cycle metrics for architecture-search
agents. Regenerate them after changing tests, task manifests, or RTL:

```bash
scripts/evaluate_candidate.sh --task yata_raintt_512_p27 \
  --results baselines/extracted-rtl/yata_raintt_512_p27.json
scripts/evaluate_candidate.sh --task hoge_streaming_intt_1024_p64 \
  --results baselines/extracted-rtl/hoge_streaming_intt_1024_p64.json
scripts/evaluate_candidate.sh --task hoge_externalproduct_ntt_1024_p64 \
  --results baselines/extracted-rtl/hoge_externalproduct_ntt_1024_p64.json
scripts/evaluate_candidate.sh --task hoge_nttid_1024_identity \
  --results baselines/extracted-rtl/hoge_nttid_1024_identity.json
scripts/evaluate_candidate.sh --task hoge_streaming_ntt_1024_p64 \
  --results baselines/extracted-rtl/hoge_streaming_ntt_1024_p64.json
scripts/evaluate_candidate.sh --task kyber_ntt_256_p12_pe1 \
  --results baselines/extracted-rtl/kyber_ntt_256_p12_pe1.json
```

Add `--with-yosys` to any command when a flattened structural resource estimate
is needed.

## Small RTL References

The `small_*` JSON files provide fixed reference metrics for the reduced HLS
bring-up targets, using real RTL references checked in under
`variants/small-ntt/rtl`:

- `small_hoge32_p64`
- `small_yata8_raintt_p27`
- `small_yata8x8_raintt_p27`

The small YATA RTL references intentionally mirror the larger RAINTT reduction
style: they use the generated `yata_sredc`/`yata_mul_sredc` datapath and no
Verilog modulo operators.

Regenerate the RTL with:

```bash
scripts/generate_small_ntt_rtl.py
```

Regenerate the baseline metrics with:

```bash
scripts/evaluate_candidate.sh --task small_hoge32_p64 \
  --results baselines/extracted-rtl/small_hoge32_p64.json
scripts/evaluate_candidate.sh --task small_yata8_raintt_p27 \
  --results baselines/extracted-rtl/small_yata8_raintt_p27.json
scripts/evaluate_candidate.sh --task small_yata8x8_raintt_p27 \
  --results baselines/extracted-rtl/small_yata8x8_raintt_p27.json
```

Add `--with-vitis` to record Vivado/Vitis resource and timing metrics using the
AutoNTT-style default `xcu280-fsvh2892-2L-e` part and `4.0 ns` clock. When
`scripts/run_small_variant_hls_synth_compare.py` is run with
`--skip-reference-synth`, it compares generated HLS results against these
checked-in RTL reference metrics instead of comparing generated results with
themselves.

## Kyber PE1 Reference

`kyber_ntt_256_p12_pe1.json` records the Verilator baseline for the
CRYSTALS-Kyber PE1 FNTT/INTT reference copied from `kyber-polmul-hw`. The task
manifest lists the PE1 auxiliary RTL files so optional Yosys/Vivado synthesis
receives the same multi-file design as the Verilator harness.
