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

For a technology-independent structural estimate, add `--with-yosys`. The
result JSON then includes `synthesis_passed`, `status.yosys`, `seconds.yosys`,
and `yosys_*` metrics from a flattened Yosys `stat -json` pass.

For FPGA-specific synthesis estimates, add `--with-vitis`. The evaluator runs
host Vivado/Vitis RTL synthesis for the task top and adds
`vitis_synthesis_passed`, `status.vitis`, `seconds.vitis`, and `vitis_*`
metrics such as LUT, FF, DSP, BRAM, URAM, timing slack, and estimated fmax. The
default target is the AutoNTT-style U280 part `xcu280-fsvh2892-2L-e` with a
`4.0 ns` clock.

If Verilator, CMake, Yosys, and SBT should come from the Apptainer image while
Vitis remains on the host, use:

```bash
scripts/evaluate_with_apptainer_and_vitis.sh --task <task> --with-yosys --sif llm-ntt.sif
```

## Runnable Tasks

| Task id | Evaluator mode | Status | Use for ranking |
| --- | --- | --- | --- |
| `yata_raintt_512_p27` | `verilator_test` | exact TFHEpp RAINTT correctness | yes |
| `hoge_streaming_intt_1024_p64` | `verilator_test` | exact TFHEpp cuHEpp INTT correctness | yes |
| `hoge_externalproduct_ntt_1024_p64` | `verilator_test` | exact TFHEpp ExternalProduct forward NTT boundary | yes |
| `hoge_nttid_1024_identity` | `verilator_test` | packed INTT/NTT identity correctness | yes |
| `hoge_streaming_ntt_1024_p64` | `lint_only` | tier0 interface/elaboration only | no arithmetic or latency ranking |

`correct = true` for a `lint_only` task only means that Verilator accepted the
required module and ports. It does not establish transform arithmetic,
coefficient order, valid burst length, or latency.

## Planned Tasks

Planned manifests live under `tasks/planned/` and are not runnable evaluator
targets, even if passed by path. They document future benchmark boundaries
without pretending an executable oracle already exists.
