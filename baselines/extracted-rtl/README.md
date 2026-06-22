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
```

Add `--with-yosys` to any command when a flattened structural resource estimate
is needed.

For host Vivado/Vitis synthesis reference results, build or provide the
Apptainer image and run:

```bash
scripts/evaluate_baselines_with_vitis.sh --sif llm-ntt.sif
```

This regenerates the Chisel-emitted golden RTL inside Apptainer, runs
correctness/Yosys there, then synthesizes each top with host Vivado using the
AutoNTT-style default `xcu280-fsvh2892-2L-e` part and `4.0 ns` clock. Use
`--vitis-part` and `--vitis-clock-period` to change the reference target.
