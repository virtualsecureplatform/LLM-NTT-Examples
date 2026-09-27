# N=512 pre-route product exploration example

This example screens complete NGen negacyclic polynomial products over a
32-bit torus before any U280 place and route. It records four objectives:
an arithmetic-error bound, Yosys generic cell count, product latency in
cycles, and sustained product initiation interval in cycles. The output
`results.json` contains every point and the nondominated screening frontier. No FPGA frequency,
U280 utilization, or FHE decryption-failure claim follows from these results.

Build the small Apptainer image and run the example from the repository root:

```bash
git submodule update --init --recursive
scripts/build_assurance_yosys.sh
scripts/build_llm_ntt_sif.sh \
  --definition apptainer/fhe512-preroute.def \
  --output build/fhe512-preroute.sif --skip-check
scripts/run_fhe512_preroute.sh --output-dir build/fhe512-preroute
```

The four-point command is a toolchain smoke campaign. For a broader pre-route
search, run the current 28-point covering grid in a separate directory:

```bash
scripts/run_fhe512_preroute.sh --grid covering \
  --output-dir build/fhe512-covering
# If interrupted, repeat with --resume and the same image, sources, and options.
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-covering \
  --evidence-file docs/measured-evidence/fhe512-covering.json
```

The earlier checked-in 22-point campaign uses indexed stream boundaries. To compare
the rectangular switch-transpose boundary against the same NGen architectures,
select `--transposes indexed switch` in a new output directory. The switch
choice adds rate-preserving input and output tensor-buffer adapters and has a
different frame interval; at N=512 it is a buffered rectangular transpose,
not the recursive square switch network. A smaller first comparison uses:

```bash
scripts/run_fhe512_preroute.sh --grid smoke --quant-bits 0 \
  --transposes indexed switch --output-dir build/fhe512-transpose-smoke
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-transpose-smoke
```

The current covering grid contains 22 NGen configurations: streamed and
stage-parallel backends, two lane counts, PE=1/2, radix 2/8, stage grouping
1/2, Barrett/Montgomery/Shoup reductions, and baseline/f300 profiles.
Six representative architectures also receive the bounded-error output
variant. This is a documented subset of the 112 configurations admitted by
the current N=512 planner, not an exhaustive sweep. The runner preserves
generator or verification failures and records RTL hashes so distinct emitted
designs can be counted.

The launcher binds the repository at its existing absolute path, sets a clean
container environment, and records the SIF SHA-256 plus tool and RTL hashes.
The image contains Java 17 for the pinned generator assemblies and Icarus
Verilog for product simulation. The launcher uses the repository's pinned
Yosys 0.50 build through the same bind mount, checks its version, and records
its binary SHA-256. Ubuntu 22.04's packaged Yosys is too old for syntax in
the generated NGen RTL. Existing
verified `third_party/NGen/ngen.bat` and, if selected,
`third_party/SGen/sgen.bat` are required. Build them with the repository's
normal `scripts/dse_release.py --stage build` command if missing.

The default workload is N=512 with near-full-range signed 32-bit inputs in
`[-2147483647,2147483647]`, negacyclic ring, and output modulo `2^32`.
This is a generic torus product, **not** a TFHE operation or an accepted FHE
noise budget. It generates two distinct three-prime NGen streamed products
(PE=1 and PE=2),
then compares exact output and output rounded to multiples of 16. Rounding
has an analytical coefficient-error bound of 8 torus units; the example
also reports observed maximum, RMS, and bias against an independent integer
schoolbook product. Output quantization is a simple, explicit bounded-error
axis for checking the search plumbing; it is not proposed as the best FHE
approximation. The default exploratory hard limit is 16 torus units.

The example runs twelve complete-product frames per point, including seeded
random inputs, under continuous traffic. It checks each output against the
specified quantized oracle and records first-to-last output latency and
sustained frame interval. It does not run the full reset/backpressure suite;
the existing exact product campaign covers that protocol separately. Yosys
processes the complete product top with process and memory lowering,
flattening, and coarse generic-cell statistics. These cell counts are only
relative screening data;
the final U280 shortlist still needs vendor synthesis and timing-clean route.

For a fast toolchain check, run the same flow at N=16:

```bash
scripts/run_fhe512_preroute.sh --n 16 --bound 7 \
  --output-dir build/fhe512-preroute-smoke
```

For a faster bounded-input N=512 pilot, use `--bound 127`; this needs one
RNS prime. `--include-sgen --bound 127` adds an exact FFT baseline (using
radix-16 digit splitting when needed); larger SGen digit grids need a
separate evaluation budget. `--quant-bits 0 4 6` and `--error-limit 32`
change the exploratory error sweep. The approximation parameter is not an
FHE noise budget: that requires a specified consuming operation and
decryption-margin analysis.

Each point has generated RTL, simulation input/output files and logs, Yosys
script/log, and a compact `point.json`. A failed generation, simulation, or
Yosys run remains visible and cannot enter the frontier. The frontier uses
the analytical error bound and all three measured screening objectives; ties
are kept. The next experiment should replace output rounding with a useful
approximate arithmetic architecture, then route the screening frontier and
a bounded near-front sample to measure actual U280 utilization and throughput.

## Initial four-point smoke run

The default N=512 campaign completed in the Apptainer image on 2026-09-24.
All four NGen points passed the twelve-frame RTL check and coarse Yosys pass:

| Point | Analytical error bound | Coarse Yosys cells | Latency cycles | Frame interval cycles |
| --- | ---: | ---: | ---: | ---: |
| PE=1, exact | 0 | 1,849,587 | 8,067 | 3,390 |
| PE=1, rounded output | 8 | 1,849,590 | 8,067 | 3,390 |
| PE=2, exact | 0 | 1,875,903 | 5,252 | 1,983 |
| PE=2, rounded output | 8 | 1,875,906 | 5,252 | 1,983 |

The screening frontier contains the two exact points. Output rounding only
adds logic here, so this trial provides no error-for-resource benefit. It
motivates changing the arithmetic implementation or precision inside the
product, rather than just rounding the final coefficient. An N=16 smoke run
also passed with the optional SGen compact baseline; N=512 SGen and U280
routing remain unmeasured.

The PE=1 and PE=2 intervals correspond to 0.295 and 0.504 products per
1,000 cycles respectively; no products-per-second rate is assigned without
timing-qualified implementation.

## N=512 covering search

The larger pre-route campaign completed on 2026-09-25. All 22 planned
products passed RTL simulation; 19 completed coarse Yosys screening, with
19 distinct RTL hashes among those measured points. The generated
`build/fhe512-covering/summary.md` report and checked-in
[full configuration metrics](measured-evidence/fhe512-covering-table.md),
[sortable CSV](measured-evidence/fhe512-covering-table.csv), and
[22-point evidence snapshot](measured-evidence/fhe512-covering.json) record
the arithmetic-error bound, observed maximum error, Yosys cells, latency,
frame interval, throughput per 1,000 cycles, and screening status for each
point. Five exact NGen designs form the resource-qualified frontier:

| Architecture | Coarse Yosys cells | Latency cycles | Frame interval cycles |
| --- | ---: | ---: | ---: |
| 2 lanes, PE=1, radix 2, Shoup | 1,849,578 | 8,067 | 3,390 |
| 2 lanes, PE=2, radix 2, Barrett | 1,875,903 | 5,252 | 1,983 |
| 2 lanes, PE=2, radix 8, Barrett | 2,667,480 | 5,004 | 2,113 |
| 4 lanes, PE=2, radix 2, Barrett | 4,650,453 | 4,484 | 1,727 |
| 4 lanes, PE=2, radix 8, Barrett | 5,535,234 | 4,236 | 2,113 |

The four output-rounded variants did not enter the frontier. Both exact
stage-parallel products passed simulation: the 2-lane point measured a
521-cycle interval, and the 4-lane point measured 1,306 latency cycles and
a 256-cycle interval. Their initial Yosys passes timed out after 900 seconds;
a second pass with a 3,600-second limit also timed out. A third pass with a
7,200-second limit completed RTL translation but timed out during Yosys
process expansion before producing cell counts. These measurements used the
earlier procedural Barrett lowering; the structural rerun below now provides
counts for the exact points. The rounded 4-lane stage-parallel Yosys
pass was stopped after the matching exact core timed out. This budget stop
is recorded separately from a tool failure.

## Rectangular switch-transpose comparison

The exact radix-2 Barrett baseline comparison now covers streamed PE=1/2 and
stage-parallel at both 2 and 4 lanes, with indexed and switch boundaries. The
`switch` boundary uses rate-preserving rectangular frame buffers at each NTT
input and output, not the lower-latency recursive network used for square
streams. All 12 points passed the same 12-frame exact-product RTL check and
completed coarse Yosys screening after the Barrett lowering was revised. The
[full 12-point matrix](measured-evidence/fhe512-transpose-matrix.md)
and [sortable CSV](measured-evidence/fhe512-transpose-matrix.csv) combine the
[indexed covering evidence](measured-evidence/fhe512-covering.json),
[2-lane switch evidence](measured-evidence/fhe512-switch-smoke.json), and
[4-lane/stage-parallel switch evidence](measured-evidence/fhe512-switch-extension.json),
plus the four structural rerun snapshots linked below. Streamed rows use the
earlier NGen RTL; stage-parallel rows use NGen commit `0f630fa`. The workload
and Yosys 0.50 coarse-memory-lowered script are the same.

```bash
scripts/run_fhe512_preroute.sh --grid smoke --transposes switch \
  --quant-bits 0 --output-dir build/fhe512-switch-512
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-switch-512 \
  --evidence-file docs/measured-evidence/fhe512-switch-smoke.json
```

The original switch extension used the following command with NGen commit
`5b04b94`. Its stage-parallel rows are superseded by the structural rerun
below; the selected configurations and tool hashes remain in the original
evidence snapshot.

```bash
scripts/run_fhe512_preroute.sh --grid covering --transposes switch \
  --quant-bits 0 --timeout 240 --output-dir build/fhe512-switch-extension \
  --configuration-names \
  ngen-streamed-l4-pe1-r2-s1-barrett-baseline-switch \
  ngen-streamed-l4-pe2-r2-s1-barrett-baseline-switch \
  ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline-switch \
  ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-switch
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-switch-extension \
  --evidence-file docs/measured-evidence/fhe512-switch-extension.json
```

NGen commit `0f630fa` emits structural Barrett butterflies and shares capture
and output multipliers per lane. The four exact stage-parallel configurations
then completed the same full-product Yosys script in 334–481 seconds. Run them
from a checkout with that NGen submodule commit using the pinned Apptainer
launcher:

```bash
for lanes in 2 4; do
  for transpose in indexed switch; do
    suffix=
    if [ "$transpose" = switch ]; then suffix=-switch; fi
    name="ngen-stage-parallel-l${lanes}-pe1-r2-s1-barrett-baseline${suffix}"
    output="build/fhe512-structural-v3-l${lanes}-${transpose}"
    scripts/run_fhe512_preroute.sh --grid covering --n 512 \
      --transposes "$transpose" --quant-bits 0 --timeout 1200 \
      --output-dir "$output" --configuration-names "$name"
    python3 scripts/report_fhe512_preroute.py --output-dir "$output" \
      --evidence-file "docs/measured-evidence/fhe512-structural-l${lanes}-${transpose}.json"
  done
done
python3 scripts/report_fhe512_transpose_matrix.py \
  docs/measured-evidence/fhe512-covering.json \
  docs/measured-evidence/fhe512-switch-smoke.json \
  docs/measured-evidence/fhe512-switch-extension.json \
  docs/measured-evidence/fhe512-structural-l2-indexed.json \
  docs/measured-evidence/fhe512-structural-l2-switch.json \
  docs/measured-evidence/fhe512-structural-l4-indexed.json \
  docs/measured-evidence/fhe512-structural-l4-switch.json \
  --prefer-later \
  --output-md docs/measured-evidence/fhe512-transpose-matrix.md \
  --output-csv docs/measured-evidence/fhe512-transpose-matrix.csv
```

The four new snapshots are
[2-lane indexed](measured-evidence/fhe512-structural-l2-indexed.json),
[2-lane switch](measured-evidence/fhe512-structural-l2-switch.json),
[4-lane indexed](measured-evidence/fhe512-structural-l4-indexed.json), and
[4-lane switch](measured-evidence/fhe512-structural-l4-switch.json).

| Backend | Lanes | PE | Boundary | Error bound | Coarse Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| streamed | 2 | 1 | indexed | 0 | 1,849,587 | 8,067 | 3,390 | 0.295 | screened |
| streamed | 2 | 1 | switch | 0 | 3,941,550 | 8,585 | 3,906 | 0.256 | screened |
| streamed | 2 | 2 | indexed | 0 | 1,875,903 | 5,252 | 1,983 | 0.504 | screened |
| streamed | 2 | 2 | switch | 0 | 3,967,110 | 5,770 | 2,499 | 0.400 | screened |
| streamed | 4 | 1 | indexed | 0 | 4,642,020 | 7,299 | 3,134 | 0.319 | screened |
| streamed | 4 | 1 | switch | 0 | 8,803,581 | 7,561 | 3,394 | 0.295 | screened |
| streamed | 4 | 2 | indexed | 0 | 4,650,453 | 4,484 | 1,727 | 0.579 | screened |
| streamed | 4 | 2 | switch | 0 | 8,812,014 | 4,746 | 1,987 | 0.503 | screened |
| stage-parallel | 2 | — | indexed | 0 | 1,943,319 | 1,818 | 521 | 1.919 | screened |
| stage-parallel | 2 | — | switch | 0 | 4,036,146 | 2,846 | 1,037 | 0.964 | screened |
| stage-parallel | 4 | — | indexed | 0 | 4,701,051 | 1,306 | 256 | 3.906 | screened |
| stage-parallel | 4 | — | switch | 0 | 8,866,410 | 1,822 | 525 | 1.905 | screened |

The buffered rectangular transpose increases both generic-cell count and frame
interval. The revised stage-parallel RTL now gives a complete coarse screening
comparison: the two indexed stage-parallel points cost about 94,000 and 51,000
more generic cells than the corresponding streamed PE=1 and PE=2 points,
respectively, while producing frames much more often. Generic Yosys cells are
not FPGA LUTs, DSPs, or BRAMs. An FPGA memory implementation, a more overlapped
wrapper, and routed timing may change these trade-offs.

## Reduction and boundary-transpose comparison

Reduction and boundary transpose are independent NGen choices. The expanded
exact-product matrix crosses Barrett, Montgomery, and Shoup with indexed and
switch boundaries for both 2 and 4 lanes. It includes streamed PE=1 for every
reduction, streamed PE=2 for Barrett, and stage-parallel for every reduction:
28 configurations in total. Every row uses the same N=512, 32-bit-torus
negacyclic workload and radix-2 baseline profile. The
[full reduction matrix](measured-evidence/fhe512-reduction-matrix.md) and
[sortable CSV](measured-evidence/fhe512-reduction-matrix.csv) give per-configuration
arithmetic error, coarse Yosys cells, latency, frame interval, and throughput
in products per 1,000 cycles. The matrix combines the earlier Barrett and
indexed streamed-reduction snapshots with the twelve new full-product runs.
All 28 rows passed the 12-frame RTL check and Yosys screening, had zero
observed error, and emitted distinct RTL hashes. The new stage-parallel
Montgomery and Shoup rows are measured with the updated structural lowering;
the earlier Barrett stage-parallel rows use NGen commit `0f630fa` and the
streamed rows come from the earlier covering and switch campaigns.

At 2 lanes with an indexed boundary, stage-parallel Montgomery uses 1,818,831
coarse cells and emits a product every 521 cycles; Shoup uses 1,833,987 cells
at the same interval, and Barrett uses 1,943,319. At 4 lanes, the corresponding
indexed counts are 4,576,491, 4,591,443, and 4,701,051, each with a 256-cycle
interval. Switching the 4-lane stage-parallel boundary adds about 4.17 million
coarse cells and changes the interval to 525 cycles for all three reductions.
The reduction choice changes the arithmetic resource estimate but not that
stage-parallel schedule; the buffered boundary changes both resources and
rate. These counts are screening estimates, not a prediction of routed U280
area or clock frequency.

From a checkout with the updated NGen submodule, reproduce the new runs in
the pinned Apptainer image and regenerate the table with:

```bash
for reduction in montgomery shoup; do
  for lanes in 2 4; do
    for transpose in indexed switch; do
      suffix=
      if [ "$transpose" = switch ]; then suffix=-switch; fi
      name="ngen-stage-parallel-l${lanes}-pe1-r2-s1-${reduction}-baseline${suffix}"
      output="build/fhe512-reduction-stage-${reduction}-l${lanes}-${transpose}"
      scripts/run_fhe512_preroute.sh --grid covering --n 512 \
        --transposes "$transpose" --quant-bits 0 --timeout 1200 \
        --output-dir "$output" --configuration-names "$name"
      python3 scripts/report_fhe512_preroute.py --output-dir "$output" \
        --evidence-file "docs/measured-evidence/fhe512-reduction-stage-${reduction}-l${lanes}-${transpose}.json"
    done
    name="ngen-streamed-l${lanes}-pe1-r2-s1-${reduction}-baseline-switch"
    output="build/fhe512-reduction-streamed-${reduction}-l${lanes}-switch"
    scripts/run_fhe512_preroute.sh --grid covering --n 512 \
      --transposes switch --quant-bits 0 --timeout 1200 \
      --output-dir "$output" --configuration-names "$name"
    python3 scripts/report_fhe512_preroute.py --output-dir "$output" \
      --evidence-file "docs/measured-evidence/fhe512-reduction-streamed-${reduction}-l${lanes}-switch.json"
  done
done
python3 scripts/report_fhe512_transpose_matrix.py \
  docs/measured-evidence/fhe512-covering.json \
  docs/measured-evidence/fhe512-switch-smoke.json \
  docs/measured-evidence/fhe512-switch-extension.json \
  docs/measured-evidence/fhe512-structural-l{2,4}-{indexed,switch}.json \
  docs/measured-evidence/fhe512-reduction-*.json \
  --prefer-later --reductions barrett montgomery shoup \
  --output-md docs/measured-evidence/fhe512-reduction-matrix.md \
  --output-csv docs/measured-evidence/fhe512-reduction-matrix.csv
```

Montgomery and Shoup stage-parallel NTTs use structural butterfly arithmetic
and shared per-lane boundary multipliers so that the full product can pass
Yosys process lowering. The matrix is a coarse pre-route comparison; its cell
counts are not U280 resources and its cycle rates cannot be converted to
products per second without timing-qualified implementation.
