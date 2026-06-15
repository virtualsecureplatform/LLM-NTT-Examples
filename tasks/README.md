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

## Runnable Tasks

| Task id | Evaluator mode | Status | Use for ranking |
| --- | --- | --- | --- |
| `yata_raintt_512_p27` | `verilator_test` | exact TFHEpp RAINTT correctness | yes |
| `hoge_streaming_intt_1024_p64` | `verilator_test` | exact TFHEpp cuHEpp INTT correctness | yes |
| `hoge_nttid_1024_identity` | `verilator_test` | packed INTT/NTT identity correctness | yes |
| `hoge_streaming_ntt_1024_p64` | `lint_only` | tier0 interface/elaboration only | no arithmetic or latency ranking |

`correct = true` for a `lint_only` task only means that Verilator accepted the
required module and ports. It does not establish transform arithmetic,
coefficient order, valid burst length, or latency.

## Planned Tasks

Planned manifests live under `tasks/planned/` and are not runnable evaluator
targets, even if passed by path. They document future benchmark boundaries
without pretending an executable oracle already exists.

- `tasks/planned/hoge_externalproduct_ntt_1024_p64.json`: future
  ExternalProduct-style HOGE forward NTT oracle using the original final
  32-bit torus output check against `TFHEpp::TwistNTT<P>`.
