# N=512 NGen/SGen common-pass frontier

The [combined table](measured-evidence/fhe512-common-frontier.md),
[CSV](measured-evidence/fhe512-common-frontier.csv), and
[evidence snapshot](measured-evidence/fhe512-common-frontier.json) compare
complete two-operand negacyclic products with near-full-range signed 32-bit
inputs and outputs modulo `2^32`. The NGen set contains the 28 exact points
in the published reduction matrix plus 12 distinct covering-grid points,
including four output-rounded variants. The SGen set contains six certified
precision/omission points. NGen products must have passed their earlier
complete-product RTL checks; the runner matches every published RTL hash
before synthesizing it.

Every resource row uses the pinned Yosys 0.50 binary and the same complete-top
`read_verilog; hierarchy; proc; flatten; memory_collect; stat; write_json`
flow. The generated memory JSON is retained locally for audit, while the
checked-in evidence records its hash and compact counts. This pass preserves
inferred memories; it does not predict U280 LUT, BRAM, DSP, clock, or routed
throughput. The historical memory-lowered NGen cell counts are not inputs to
the combined frontier.

The old four-lane stage-parallel rounded RTL from the covering grid was emitted
before the structural NGen lowering and stalled during Yosys frontend
translation. The same rounded configuration is regenerated from the current
NGen backend and must pass the 12-frame product check before inclusion. Its
new RTL hash and campaign result are pinned in the synthesis manifest.

From the repository root, after reproducing the NGen campaigns described in
[the pre-route example](fhe512-preroute-example.md) and building the
[SGen precision image](fhe512-sgen-precision.md), run:

```bash
scripts/run_fhe512_preroute.sh --grid covering --n 512 \
  --transposes indexed --quant-bits 4 --timeout 1200 \
  --output-dir build/fhe512-common-q4-refresh \
  --configuration-names ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline
scripts/run_fhe512_common_synth.sh --output-dir build/fhe512-common-synth-final3 \
  --workers 4 --timeout 1200
# Repeat with --resume if interrupted; workers and timeout may be changed.
python3 scripts/report_fhe512_common_frontier.py \
  --ngen-results build/fhe512-common-synth-final3/results.json \
  --sgen-evidence docs/measured-evidence/fhe512-sgen-precision.json \
  --output-md docs/measured-evidence/fhe512-common-frontier.md \
  --output-csv docs/measured-evidence/fhe512-common-frontier.csv \
  --evidence-file docs/measured-evidence/fhe512-common-frontier.json
```

The checked-in snapshot reused 40 previously screened rows with matching RTL,
image, Yosys, and pass hashes; its manifest records the reused results hash.
The command above remeasures the rows from scratch and produces the same
resource and frontier metrics. Use `--reuse-from <prior-results.json>` to
perform a hash-checked reuse instead.

The analytical coefficient-error bound, generic cells, retained memory bits,
register bits, multiplier operators, latency cycles, and frame interval cycles
are seven separate minimization objectives. A point is dominated only if
another is no worse in every objective and strictly better in at least one.
Throughput in products per 1,000 cycles is calculated from the frame interval
and is not an additional objective. The report also recomputes the frontier
under exact arithmetic and an error limit of eight torus units. Equal metric
vectors remain visible as ties, because they are distinct tested RTL designs.
The error bound is a per-coefficient arithmetic bound, not an FHE noise budget.

The completed sweep screened **40/40 NGen** and **6/6 SGen** points. The
seven-objective frontier has **13** points: ten exact NGen products and the
three 30-bit SGen precision/omission variants. The exact-only frontier has
**11** points, including the exact 30-bit SGen product. All four NGen
output-rounded points are dominated, so allowing an eight-unit error does
not change that frontier. Allowing the larger SGen omission bounds adds two
latency/error tradeoffs.

The exact SGen point survives the resource-aware frontier because it has
fewer multiplier operators and fewer retained memory bits than the streamed
NGen reference, despite its much longer 505,844-cycle frame interval. For a
throughput-oriented U280 shortlist, that extreme point should be evaluated
against explicit resource and throughput constraints rather than selected
solely because it is nondominated. Memory port structure and FPGA timing are
not captured by the seven coarse metrics; vendor synthesis is needed before
interpreting this frontier as hardware utilization or products per second.
