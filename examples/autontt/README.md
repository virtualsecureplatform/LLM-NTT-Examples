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
