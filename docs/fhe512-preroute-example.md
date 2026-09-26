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
search, run the 22-point covering grid in a separate directory:

```bash
scripts/run_fhe512_preroute.sh --grid covering \
  --output-dir build/fhe512-covering
# If interrupted, repeat with --resume and the same image, sources, and options.
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-covering \
  --evidence-file docs/measured-evidence/fhe512-covering.json
```

The checked-in 22-point campaign uses indexed stream boundaries. To compare
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

The covering grid contains 18 NGen configurations: streamed and
stage-parallel backends, two lane counts, PE=1/2, radix 2/8, stage grouping
1/2, Barrett/Montgomery/Shoup reductions, and baseline/f300 profiles.
Four representative architectures also receive the bounded-error output
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
process expansion before producing cell counts, so they cannot be compared
for resource-constrained selection. The rounded 4-lane stage-parallel Yosys
pass was stopped after the matching exact core timed out. This budget stop
is recorded separately from a tool failure. These results motivate a more
scalable resource estimator for stage-parallel hardware before promoting it
into a routed shortlist.

## Rectangular switch-transpose comparison

The exact radix-2 Barrett baseline comparison now covers streamed PE=1/2 and
stage-parallel at both 2 and 4 lanes, with indexed and switch boundaries. The
`switch` boundary uses rate-preserving rectangular frame buffers at each NTT
input and output, not the lower-latency recursive network used for square
streams. All 12 points passed the same 12-frame exact-product RTL check; eight
completed coarse Yosys screening. The [full 12-point matrix](measured-evidence/fhe512-transpose-matrix.md)
and [sortable CSV](measured-evidence/fhe512-transpose-matrix.csv) combine the
[indexed covering evidence](measured-evidence/fhe512-covering.json),
[2-lane switch evidence](measured-evidence/fhe512-switch-smoke.json), and
[4-lane/stage-parallel switch evidence](measured-evidence/fhe512-switch-extension.json).

```bash
scripts/run_fhe512_preroute.sh --grid smoke --transposes switch \
  --quant-bits 0 --output-dir build/fhe512-switch-512
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-switch-512 \
  --evidence-file docs/measured-evidence/fhe512-switch-smoke.json
```

The four additional switch points use the following command. The selected
configurations and tool hashes are recorded in
`build/fhe512-switch-extension/manifest.json` when run locally.

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
python3 scripts/report_fhe512_transpose_matrix.py \
  docs/measured-evidence/fhe512-covering.json \
  docs/measured-evidence/fhe512-switch-smoke.json \
  docs/measured-evidence/fhe512-switch-extension.json \
  --output-md docs/measured-evidence/fhe512-transpose-matrix.md \
  --output-csv docs/measured-evidence/fhe512-transpose-matrix.csv
```

To extend Yosys screening for the four simulated stage-parallel points without
repeating generation or RTL simulation, use the pinned Apptainer image and the
existing campaign directories:

```bash
apptainer exec --cleanenv --no-home --pwd "$(pwd)" --bind "$(pwd):$(pwd)" \
  build/research-tools.sif python3 scripts/refresh_fhe512_yosys.py \
  --output-dir build/fhe512-covering --timeout 7200 --configuration-names \
  ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline \
  ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline
apptainer exec --cleanenv --no-home --pwd "$(pwd)" --bind "$(pwd):$(pwd)" \
  build/research-tools.sif python3 scripts/refresh_fhe512_yosys.py \
  --output-dir build/fhe512-switch-extension --timeout 7200 --configuration-names \
  ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline-switch \
  ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-switch
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-covering \
  --evidence-file docs/measured-evidence/fhe512-covering.json
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-switch-extension \
  --evidence-file docs/measured-evidence/fhe512-switch-extension.json
python3 scripts/report_fhe512_transpose_matrix.py \
  docs/measured-evidence/fhe512-covering.json \
  docs/measured-evidence/fhe512-switch-smoke.json \
  docs/measured-evidence/fhe512-switch-extension.json \
  --output-md docs/measured-evidence/fhe512-transpose-matrix.md \
  --output-csv docs/measured-evidence/fhe512-transpose-matrix.csv
```

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
| stage-parallel | 2 | — | indexed | 0 | — | 1,818 | 521 | 1.919 | Yosys timeout (7,200 s) |
| stage-parallel | 2 | — | switch | 0 | — | 2,846 | 1,037 | 0.964 | Yosys timeout (7,200 s) |
| stage-parallel | 4 | — | indexed | 0 | — | 1,306 | 256 | 3.906 | Yosys timeout (7,200 s) |
| stage-parallel | 4 | — | switch | 0 | — | 1,822 | 525 | 1.905 | Yosys timeout (7,200 s) |

The buffered rectangular transpose increases both generic-cell count and frame
interval for the streamed points. Stage-parallel resource usage remains
unmeasured: all four full-product Yosys runs timed out with a 7,200-second
limit during process expansion after RTL translation. The stage-parallel RTL
needs a more scalable synthesis representation before these rows can be ranked
by resource usage. An FPGA memory implementation, a more overlapped wrapper,
and routed timing may change these trade-offs.
