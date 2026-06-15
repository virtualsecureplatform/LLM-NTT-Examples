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
