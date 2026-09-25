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
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-covering
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
a 256-cycle interval. Their Yosys passes timed out after 900 seconds before
producing cell counts, so they cannot be compared for resource-constrained
selection. The rounded 4-lane stage-parallel Yosys pass was stopped after
the matching exact core timed out. This budget stop is recorded separately
from a tool failure. These results motivate a more scalable resource
estimator for stage-parallel hardware before promoting it into a routed
shortlist.

## Rectangular switch-transpose comparison

An additional N=512 Apptainer run measured the exact 2-lane Barrett streamed
smoke designs with the new `switch` boundary. This is a rate-preserving,
frame-buffered 256-cycle × 2-lane rectangular transpose at each NTT input and
output, not the lower-latency recursive network used for square streams. All
four rows below passed the same 12-frame exact-product RTL check and completed
coarse Yosys screening. The [switch report](measured-evidence/fhe512-switch-smoke.md),
[CSV](measured-evidence/fhe512-switch-smoke.csv), and
[evidence snapshot](measured-evidence/fhe512-switch-smoke.json) preserve both new points.

```bash
scripts/run_fhe512_preroute.sh --grid smoke --transposes switch \
  --quant-bits 0 --output-dir build/fhe512-switch-512
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-switch-512
```

| PE | Boundary | Coarse Yosys cells | Product latency cycles | Frame interval cycles | Products / 1,000 cycles |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | indexed | 1,849,587 | 8,067 | 3,390 | 0.295 |
| 1 | switch | 3,941,550 | 8,585 | 3,906 | 0.256 |
| 2 | indexed | 1,875,903 | 5,252 | 1,983 | 0.504 |
| 2 | switch | 3,967,110 | 5,770 | 2,499 | 0.400 |

Here the buffered rectangular transpose increases both generic-cell count and
frame interval. It establishes a functional comparison point, not a claim that
switch transpose is inherently worse: an FPGA memory implementation, a more
overlapped wrapper, and routed timing may change the trade-off. Stage-parallel
switch variants are now legal but have not been screened at N=512.
