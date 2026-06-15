# Task Manifests

Each JSON file in this directory describes one benchmark task for an
architecture-search or LLM-generation agent.

The evaluator script accepts either a task id or a path:

```bash
scripts/evaluate_candidate.sh --task hoge_streaming_intt_1024_p64
scripts/evaluate_candidate.sh --task tasks/yata_raintt_512_p27.json
```

For candidate Verilog, pass a directory containing the expected top-level file:

```bash
scripts/evaluate_candidate.sh \
  --task hoge_streaming_intt_1024_p64 \
  --verilog-dir candidate/hoge-intt
```

If `--verilog-dir` is omitted, the evaluator uses the extracted baseline RTL
listed in the manifest.
