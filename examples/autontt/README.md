# AutoNTT Example Inputs

This directory contains adapter material for using the LLM-NTT tasks as
AutoNTT-style architecture-search problems.

The most direct match is HOGE:

```bash
cd ../../AutoNTT/automation_framework
python3 AutoNTT.py \
  --poly_size 1024 \
  --mod_size 64 \
  --resources fpga_resources.json \
  --arch_type IDH \
  --modmul_type C \
  --custom_mod_kernel ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_kernel.txt \
  --custom_mod_host ../../LLM-NTT-Examples/examples/autontt/custom_reductions/hoge_p64/custom_red_host.txt
```

AutoNTT output still needs a wrapper before it can be evaluated by
`scripts/evaluate_candidate.sh`, because AutoNTT emits TAPA/Vitis HLS kernels
rather than the exact Verilog top modules used by the task manifests.

YATA is documented in `custom_reductions/yata_p27/`, but it is not a direct
AutoNTT input because this extracted task uses `N = 512`.

## LLM RTL Generator

`llm_rtl_generator/` contains a pure-Python generator that maps each task
manifest onto AutoNTT-style search points and asks an OpenAI-compatible LLM
endpoint to emit Verilog matching the task interface.

List the server models:

```bash
../../scripts/autontt_llm_generate.py \
  --endpoint http://<openai-compatible-endpoint>/v1 \
  --list-models
```

Inspect the search points for a task:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --plan-only
```

Generate and evaluate one candidate:

```bash
../../scripts/autontt_llm_generate.py \
  --task hoge_streaming_intt_1024_p64 \
  --endpoint http://<openai-compatible-endpoint>/v1 \
  --arch-type IDH \
  --modmul-type AUTO \
  --attempts 1
```

Useful options:

- `--strategy behavioral_reference`: ask for a simulation-oriented baseline.
- `--with-yosys`: run the optional structural estimate after correctness.
- `--extra-instruction "..."`
  adds task-specific guidance to the prompt.
- `--extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}'`
  passes server-specific request fields to local OpenAI-compatible runtimes.

Runs are stored under `build/llm-runs/<task-id>/<timestamp>/`. Each attempt
contains the prompt, raw LLM response, extracted Verilog, evaluator stdout, and
`results.json` when evaluation ran.

The endpoint can also be supplied with `LLM_NTT_LLM_ENDPOINT` to avoid recording
private hostnames in command histories or documentation.
