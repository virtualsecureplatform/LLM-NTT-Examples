# AutoNTT Adapter Notes

AutoNTT and this repository are complementary:

- AutoNTT searches HLS NTT accelerator architectures and emits TAPA/Vitis HLS.
- This repository provides small RTL/Verilator tasks with TFHEpp references and
  fixed top-level Verilog contracts.

The best direct overlap is the HOGE `N = 1024`, 64-bit-prime setting. YATA is
still useful as an LLM RTL-generation task, but it is not a direct AutoNTT input
because the extracted YATA example uses `N = 512`, while AutoNTT's documented
range starts at `N = 1024`.

## Mapping HOGE To AutoNTT

HOGE streaming INTT task:

```text
LLM-NTT task: hoge_streaming_intt_1024_p64
AutoNTT poly_size: 1024
AutoNTT mod_size: 64
Prime: 0xffffffff00000001
Interesting reduction: custom pseudo-Mersenne reduction
Architectures: iterative, dataflow, hybrid
```

Example AutoNTT command shape:

```bash
cd ../AutoNTT/automation_framework
python3 AutoNTT.py \
  --poly_size 1024 \
  --mod_size 64 \
  --resources fpga_resources.json \
  --arch_type IDH \
  --modmul_type C \
  --custom_mod_kernel ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_kernel.txt \
  --custom_mod_host ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_host.txt
```

AutoNTT emits HLS, not the exact RTL top modules expected by this repository.
To compare an AutoNTT result against these tasks, add a wrapper that adapts the
AutoNTT generated interface to the task manifest's Verilog ports and stream
ordering.

## What To Compare

Useful comparisons:

- AutoNTT iterative vs HOGE extracted streaming RTL.
- AutoNTT dataflow vs HOGE extracted streaming RTL.
- Barrett vs Montgomery vs WLM vs HOGE pseudo-Mersenne custom reduction.
- Different butterfly-unit budgets under the same resource file.
- Different target latency or throughput constraints.

Use correctness-tested HOGE tasks for these comparisons. The extracted
`hoge_streaming_ntt_1024_p64` task is lint-only and should remain an interface
gate until an ExternalProduct-style forward NTT oracle is implemented.

## YATA Gap

YATA has two properties that make it valuable for LLM-based RTL search even
though it is not a direct AutoNTT fit:

- `N = 512`, smaller than AutoNTT's documented range.
- signed 27-bit compressed RAINTT arithmetic with `P = 5^4 * 2^16 + 1`.

Possible extensions:

- Add an AutoNTT small-N mode for `N = 512`.
- Add a custom signed reduction model compatible with YATA's RAINTT arithmetic.
- Treat YATA as the RTL-only benchmark and HOGE as the AutoNTT-aligned
  benchmark.

## Integration Boundary

Keep the boundary explicit:

- AutoNTT is the architecture-search engine.
- `tasks/*.json` are the benchmark problem statements.
- `scripts/evaluate_candidate.sh` is the correctness and metrics oracle.
- Candidate adapters are responsible for matching top-level ports and stream
  ordering.
- Planned manifests under `tasks/planned/` describe future targets and are not
  evaluator-ready tasks.
