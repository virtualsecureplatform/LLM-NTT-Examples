# Runnable NGen/SGen polynomial-product DSE

This implements the bounded-integer first release of the
[research plan](ntt-fft-dse-plan.md). It extends the existing campaign runner;
it does not replace the generic-transform or preset workloads. NGen and SGen
are pinned Git submodules under `third_party/`, alongside TFHEpp.
The [first-release validation results](product-dse-results.md) record the completed
functional matrix and matched routed measurements.

## Build and run

Use Python 3.9 or newer, a JDK supported by sbt (JDK 21 was used here), sbt,
Icarus Verilog (`iverilog` and `vvp`), Verilator and a C++ compiler. The full
legacy regression also needs CMake and a Clang supporting `_BitInt`.
Install these tools or put them on `PATH`; the release script does not silently
install dependencies or download binaries. Generator assemblies are built from
source and checked against embedded source manifests before use. The build
stage also regenerates the legacy YATA/HOGE Chisel RTL needed by the existing
Python regression; these generated files are not tracked in Git.

```bash
git submodule update --init --recursive
python3 scripts/dse_release.py --stage check
python3 scripts/dse_release.py --stage build
python3 scripts/dse_release.py --stage smoke
python3 scripts/dse_release.py --stage matrix
python3 scripts/dse_release.py --stage hardware
python3 scripts/dse_release.py --stage report
```

`--stage all` executes that sequence. `--output-dir build/my-release` chooses
another release directory. `--resume` skips completed work only when the
campaign, source, generator binaries, tools, policy and constraints match the
saved manifest. Use a new directory after changing sources or tools. A failed
or incomplete release report exits nonzero. Individual simulation stages do
not imply completion of the hardware release.

The hardware release uses Vivado 2023.2 and `xcu280-fsvh2892-2L-e`, initially
at 4 ns. The normal installation path is
`/home/opt/xilinx/Vivado/2023.2/bin/vivado`; custom search campaigns can set
`target.vivado`. If the 4 ns campaign lacks a timing-clean routed result from
each generator, the driver runs a separate matched 8 ns campaign. Results at
different periods are never combined into a single frontier. A working license
and sufficient machine resources are necessary for that stage. Hardware campaigns
insert one identity LUT per primary input (except the clock) using the existing
OOC hold-repair helper. This provides a physical path for input hold repair,
preserves logical behavior and counts in reported utilization; both setup and
hold must pass.

For a single campaign, without the release sequence:

```bash
python3 scripts/search_architectures.py \
  --campaign campaigns/product-smoke.json --output-dir build/product-smoke --mode plan
python3 scripts/search_architectures.py \
  --campaign campaigns/product-smoke.json --output-dir build/product-smoke --mode run
python3 scripts/search_architectures.py \
  --campaign campaigns/product-smoke.json --output-dir build/product-smoke --mode report
```

Products support enumeration and seeded random selection. LLM and learned cost
policies remain available for the older workloads, but are intentionally not
accepted for products until their feature and cost models are extended.
`--ngen-root` and `--sgen-root` override the default submodules for development.
An SGen-only product campaign requires only SGen's verified assembly.

## Exact workload and interface

Version 1 computes `a(x) * b(x) mod (x^N + 1)` over **integers**, for
`N ∈ {8, 16, 32, 64, 256}` and independently bounded coefficients `[-7, 7]`.
Every transaction supplies two fresh operands. A coefficient is encoded as a
signed four-bit value; `-8` is outside the contract. The output coefficient
width is `1 + bit_length(49*N)`. Wider coefficients, arbitrary moduli, cyclic
products, operand reuse, TFHE torus semantics and approximate outputs require
new contracts and are rejected by this release's product validator.

The generated top is `SearchTop`:

| Port | Meaning |
| --- | --- |
| `clock`, `reset` | Rising-edge clock and synchronous active-high reset |
| `in_valid`, `in_ready` | Joint handshake for both operands |
| `a[7:0]`, `b[7:0]` | Two consecutive signed coefficients per operand; lower index in low nibble |
| `out_valid`, `out_ready` | Output handshake with stable data while stalled |
| `out_data[2*OW-1:0]` | Two consecutive signed result coefficients, lower index in low bits |

A frame has `N/2` input beats and `N/2` output beats. Reset discards all
in-flight frames. Buffering converts each generator's lane count and protocol
to this common interface, reserves output storage before launching a core,
and honors its declared frame spacing. FFT token pipelines are flushed before
accepting post-reset input. Wrapper scheduling and buffering overhead is
included in measured latency, interval and area.

## Generated architectures

| Backend | Product construction | Explored axes |
| --- | --- | --- |
| NGen streamed | Two forward negacyclic NTTs, pointwise field products, one inverse NTT | Lanes 2/4, PE 1/2, legal radices 2/4/8, stage groups 1/2, reduction, profile |
| NGen stage-parallel | Same product with stage-parallel cores | Lanes 2/4, radix 2, reduction, profile |
| NGen fully-parallel | Same product with full-vector cores and frame adapters | Lanes N, radix 2, Barrett, profile |
| SGen full-throughput | Two zero-padded length-2N FFTs, complex products, inverse FFT, normalization and negacyclic fold | Lanes 2/4, radix 2, fractional bits 16/24/32, guard bits 0/2 |
| SGen compact | Same product with iterative Pease FFTs | Same numerical and lane axes |

NGen uses `q=65537`, a validated primitive `2N`-th root and `q > 2*N*7²`.
Centered conversion therefore recovers the unique bounded integer result.
Reductions are Barrett, Montgomery, Shoup or the generator's `auto` choice;
profiles are `baseline` and `f300`. The names describe actual generator options,
not an assertion of equivalence to AutoNTT's architecture categories.

SGen uses `CTDFT/ICTDFT` or `ItPeaseFused/IItPeaseFused`, unit scale, dual RAM
control and fixed-point complex arithmetic. Integer bits are sized conservatively
for the unnormalized product, with optional extra guards. Generated metadata
records format, twiddle bits, timing, packing, arithmetic rules and RTL hashes.
The opt-in strict fixed-point mode prevents optimizations that move a negation
across a truncating multiplication. Fixed-point constant scaling uses an exact
integer power of two, including at widths above binary64's integer precision.

The complete product has three transform engines; it does not claim shared
forward/inverse hardware, in-place memory, or AutoNTT's combined-core cost.

## Numerical qualification and correctness

The FFT certificate is a conservative rational arithmetic bound, not a
statistical error estimate. It encloses π and the sine/cosine values independently,
compares those intervals with the emitted twiddle table, propagates rounding
and coefficient errors through both forward transforms, multiplication and the
inverse, and checks intermediate range. Certification requires a final absolute
error **strictly below 1/2**. The widened fold normalizes by an exact power of
two and rounds to nearest, ties to even.

This is an arithmetic-model certificate, **not a formal RTL equivalence proof**.
Independent integer models of both FFT factorizations check every intermediate
FFT and pointwise result bit-for-bit in RTL simulation. All backends are also
checked against an independent integer schoolbook negacyclic convolution.
Qualification is tied to the workload, descriptors, generator cores and complete
product RTL; report generation and hardware admission recheck these artifacts.

The corpus contains 49 Cartesian combinations of zero, impulses, maximal signed,
alternating and sparse operands plus 256 seeded random pairs. Simulation includes
a continuous 305-product stream, source/sink stalls, extra-output detection,
watchdogs and resets during capture, arithmetic and stalled output. Insufficient
precision is recorded as `numerically_unqualified`, never a correct or Pareto
candidate. Every accepted candidate must pass the arithmetic and RTL gates.

## Release coverage, budgets and evidence

`architecture_search/release.py` defines deterministic covering configurations:

- Smoke: six configurations covering all five backends and streamed PE 1/2.
- Matrix: N=8/16/32/64/256, covering lanes, legal radices, stage groups,
  all declared reductions/profiles and FFT precision/guard choices. This is a
  covering matrix, not the Cartesian product of every axis.
- Hardware: all six smoke configurations are simulated and synthesized. Routing
  selects up to two configurations per generator: the smallest synthesized LUT
  count and the shortest measured frame interval (duplicates collapse).

Default budgets are two hours for smoke, 2.4 hours for each size's functional
matrix, and twelve hours for each hardware campaign, with six synthesis and
four routing slots. Budgets and failures remain visible; exhausting a budget
cannot pass release acceptance. N=64 and N=256 use Verilator to keep larger simulations practical; smaller
matrices use Icarus. Full-vector compilation at N=256 can still be slow.

Each campaign stores `manifest.json`, generator executable snapshots,
`state.json`, per-candidate RTL/metadata/certificates/test inputs/logs, and
`report.json`/`report.md`. The aggregate `release-report.json` requires every
covering point to be accounted for, no functional failures, qualified results
for all backends, and a matched campaign with timing-clean routed results from
both generators. Duplicate RTL and rejected numerical points stay visible.

Latency is from the first accepted input beat to the last accepted output beat
of the first product. First-output and maximum loaded latencies are also saved.
Steady frame interval is measured after warmup under continuous traffic.
Hardware rates use **completed products per second**, the whole product RTL,
and timing-qualified clocks. Optional bandwidth limits count both four-bit
input operands and every full-width output coefficient.

These are routed FPGA-fabric measurements, not board measurements, CPU-to-FPGA
throughput, or a demonstration of superiority over AutoNTT. Publication-scale
comparisons, analytical-search baselines and broader numerical workloads remain
in the research roadmap.
