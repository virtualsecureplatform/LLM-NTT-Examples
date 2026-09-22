# Product research implementation

Baseline: `77512ac`. This is the accepted follow-up to the bounded product
release. Milestones are complete only when their evidence gates pass.

| Milestone | Implementation | Required evidence | Status |
| --- | --- | --- | --- |
| M1 assurance | Lowered SGen operation contracts, independent RTL/contract audit, primitive proofs, qualification binding | Mutation rejection, actual-width proofs, complete product regression | In progress |
| M2 scale | Matched N=16/64/256 U280 campaigns at 8 ns, separate 16 ns fallback; diagnose fully parallel timing | Six syntheses/four routes per size/period; qualified pair per size | Pending |
| M3 search | Analytical and product cost policies, integrity-checked reuse, replay and fresh trials | Freeze on N=16/64 before N=256 hardware; no observation leakage | Pending |
| M4 arithmetic | Version-2 integer/modular linear/cyclic/negacyclic products, CRT and FFT splitting, exact TFHEpp adapter | Independent exact checks including N=1024 modulo 2^32 | Pending |
| M5 board | Common XRT wrapper for selected N=64 NTT/FFT products | All outputs checked, batches 1/16/256/4096, two warmups/ten repetitions | Pending |
| M6 research | Pinned AutoNTT, matched transform comparison, ablations, portable evidence bundle | Measured boundary-matched results, failures retained | Pending |

## Decisions

- Layered verification, not a claim of end-to-end formal FFT equivalence.
- NGen/SGen remain pinned submodules. Publish generator commits before parent pins.
- Preserve version-1 campaigns and historical assurance levels.
- Vivado 2023.2, U280 xcu280-fsvh2892-2L-e, common OOC input hold repair.
- Hardware budget: 24 hours, six synthesis/four route slots per size/period;
  fully parallel timing repair gets two additional synthesis/route slots.
- Search baselines: enumeration, seeded random, analytical, learned cost.
  Replay budgets 4/8/16 and seeds 0–19. Fresh N=64 trials: seeds 0–2,
  four synthesis evaluations/six hours each, no cross-trial measurement reuse.
- NTT prime catalog: 65537, 469762049, 1811939329, 2013265921; choose the
  fewest compatible primes, then smallest product, with Q > 2NAB.
- FFT splitting uses radix 16, sequential digit products, exact accumulation;
  fractions 24/32/40/48, guards 0/2. Insufficient precision is rejected.
- TFHEpp target: USE_CGGI19/lvl1param, N=1024, exact negacyclic product
  modulo 2^32. Python integer convolution and PolyMulNaive are the oracles.
- Board platform: xilinx_u280_gen3x16_xdma_1_202211_1. Count adapters;
  report kernel and transfer-inclusive timings separately.
- AutoNTT pin: de1db3fa39d88350c0b69d19f30b1fdcaef6a002. Compare N=1024
  Goldilocks/custom and N=16384 54-bit Barrett with identical field semantics.
  Preloaded compute comparison includes both directions, storage and adapters;
  initialization and published off-chip measurements remain separate.
- Full bootstrapping, external products, LLM product search and N=1024 routing
  are outside this bounded roadmap.

## Execution order and failure policy

M1; M2 at N=16/64; M3 development/freeze; M2/M3 at N=256; M4; M5; M6.
AutoNTT preparation can occur earlier. Retain the existing 130-point regression,
protocol stress, intermediate FFT checks and clean-checkout reproduction.
Timeouts, tool failures and exhausted budgets leave their milestone incomplete.
No gate requires a favorable performance result or superiority claim.

## Runnable entry points

Initialize dependencies and build their recorded assemblies first:

```sh
git submodule update --init --recursive
(cd third_party/NGen && sbt test assembly)
(cd third_party/SGen && sbt test assembly)
scripts/build_assurance_yosys.sh
export PATH="$PWD/build/tools/bin:$PATH"
python3 scripts/dse_release.py --stage check
```

The assurance stages require Yosys **0.50**, Icarus, and Verilator
with a C++20 compiler on `PATH`. Yosys proofs fail closed on another version.
The optional Yosys builder pins source commit
`b5170e1394f602c607e75bdbb1a2b637118f2086` and needs Git, Make, g++,
Bison, Flex, and Python. The validation host uses repository-local tools under `build/tools/bin`; that
installation is deliberately not selected implicitly. Vivado/Vitis 2023.2 and
the U280 platform/XRT are required for implementation and board stages.

Run each stage in an immutable checkout. A saved campaign rejects a changed
source/tool identity on resume. `--resume` retains completed records and failure
artifacts; use a new output directory when changing code or campaign definitions.

```sh
python3 scripts/dse_release.py --stage assurance --output-dir build/research
python3 scripts/dse_release.py --stage scaled-hardware --sizes 16 64 --output-dir build/research
python3 scripts/dse_release.py --stage timing-repair --output-dir build/research
python3 scripts/product_search_study.py --stage characterize --sizes 16 64 --output-dir build/research
python3 scripts/dse_release.py --stage freeze-search --output-dir build/research
python3 scripts/dse_release.py --stage scaled-hardware --sizes 256 --output-dir build/research
python3 scripts/product_search_study.py --stage characterize --sizes 256 --output-dir build/research
python3 scripts/product_search_study.py --stage fresh --output-dir build/research
```

The covering pools expose all implementation observations only to the offline
reference frontier. Acquisition receives configuration, generated structure,
functional interval, and previously observed synthesis results. Learned
predictions are three-neighbor estimates within a generator; their neighbor
range is **not** a confidence interval. Neither prediction nor a cache hit can
establish functional qualification. Cache use is opt-in through
`search_architectures.py --cache-dir`; fresh policy trials omit it.

```sh
python3 scripts/product_search_study.py --stage replay \
  --report build/research/pool-64/report.json --output-dir build/research/replay-64
python3 scripts/product_search_study.py --stage ablations \
  --report build/research/pool-64/report.json --output-dir build/research/ablations-64
python3 scripts/wide_product_study.py --stage coverage --output-dir build/research/wide
python3 scripts/wide_product_study.py --stage tfhe --output-dir build/research/wide
```

Repeat replay/ablation reporting for each measured pool. Ablations compare only
configurations that differ in one declared factor and retain missing pairs as
unmeasured. The TFHE stage runs both exact oracles, RTL simulation, and synthesis;
it does not require routing the N=1024 products.

Version-2 workload examples are produced by `wide_products.workload()` and
`wide_products.tfhe_workload()`. Each operand has its own inclusive integer
range. Nonnegative operands use unsigned encoding; ranges containing negative
values use two's-complement encoding. Products support `linear`, `cyclic`, and
`negacyclic` rings, with optional final modular reduction. Linear output has
`2*N-1` coefficients; its final two-lane beat has a zero padding lane. Radix-16
FFT digit products reuse one three-transform product engine sequentially.
The adapter in `include/tfhepp_exact_product.hpp` exposes an explicit transport
callback; it does not replace TFHEpp's existing multiplication implementation.

Select the fastest qualified routed N=64 point per generator at the same clock:

```sh
python3 scripts/product_board.py --stage select \
  --report build/research/scaled-64-8ns/report.json --output-dir build/research/board
python3 scripts/product_board.py --stage build \
  --report build/research/scaled-64-8ns/report.json --output-dir build/research/board
python3 scripts/product_board.py --stage run \
  --report build/research/scaled-64-8ns/report.json --output-dir build/research/board
```

Use the separate 16 ns report if the 8 ns campaign has no qualified pair. The
build includes identical HLS memory movers, AXI streams, batch counters, and HBM
connections. The link gate checks actual setup/hold slack and the product clock,
and retains hierarchical utilization for the complete wrapper. Host allocation
and oracle calculation are outside transfer-inclusive timing; buffer transfers,
kernel launches, completion waits, and result transfer are inside it. Hardware
cycles cover first accepted input through final accepted product output. Trailer
transfers are included only in transfer-inclusive timing. Every coefficient in
all 48 warm-up/measured batches is checked; trailer traffic is counted.

```sh
scripts/check_autontt_hls_deps.sh
python3 scripts/autontt_research.py --stage probe --output-dir build/research/autontt
python3 scripts/autontt_research.py --stage trace --architecture I \
  --design PATH_TO_GENERATED_DESIGN --output-dir build/research/autontt-trace
python3 scripts/autontt_research.py --stage prepare-ngen \
  --trace build/research/autontt-trace/trace.json --output-dir build/research/matched-field
```

AutoNTT tracing instruments a copy of its generated host after successful kernel
checks. It verifies actual forward/inverse outputs against the independent
integer oracle, accounting for the pinned iterative host's bit-reversed forward
output and the D/H host's natural output. Field-matched NGen campaigns retain
actual architecture metadata; I/D/H labels do not establish structural identity.
Ordinary streaming measurements from these campaigns are **not** automatically
preloaded-compute comparisons. The comparison gate requires separately measured
preloaded adapters, counted storage/permutation/control, measured BU provenance,
matching fields/directions/targets, and sealed functional/routed evidence. The
complete preloaded AutoNTT adapter still needs implementation and validation once
the TAPA runtime is available; M6 remains incomplete until that gate passes.

Export evidence without rewriting its original measurement hashes:

```sh
python3 scripts/product_evidence_bundle.py --reports \
  build/research/assurance.json build/research/scaled-hardware.json \
  --output-dir build/research-bundle
python3 scripts/product_evidence_bundle.py --verify --output-dir build/research-bundle
```

The bundle stores content-addressed files and an original-path map. Verification
works after relocation without the original files. Bundle integrity does not
mean a milestone passed; failed and incomplete experiments remain visible.

Use `python3 scripts/product_research_status.py --output-dir build/research`
to summarize milestone acceptance artifacts. Missing measurements remain
incomplete, including the full matched AutoNTT adapter gate.

## Validation record (2026-09-22, still in progress)

- SGen: 148 generator tests passed; exported lowered full/compact graphs audited.
- NGen: 162 generator tests passed, including direct DFT comparison of split
  Barrett forward/inverse RTL with bubbles and reset.
- Framework: 191 tests passed; targeted checks also passed after subsequent
  comparison-provenance and cache-input validation tightening.
- M1 matrix: N=8/16/32/64 passed; N=256 still running in immutable snapshot
  `2f21969`. Deliberately insufficient FFT precision is rejected and accounted.
- Wide functional checks: both generators passed all three rings at N=8/bound
  127, direct linear N=16/bound 7, and multi-prime N=16/bound 32767.
- Exact TFHEpp/Python: all 100 N=1024 corpus products agreed. NGen RTL passed;
  the SGen split-product RTL simulation is still running.
- Board wrapper: backpressure, three consecutive batches, trailer ordering,
  output stability, and counters passed Icarus. XRT host compiled; RTL XO
  packaging and both HLS memory-mover compile smoke checks succeeded. Full
  board linking and measurements require the qualified N=64 pair.
- AutoNTT: N=16384/54-bit Barrett I/D/H source generation succeeded. All custom
  Goldilocks measured-BU probes failed in C simulation. Dependency checks found
  missing `tapac`, `tapacc`, `tapa`, `tapa.h`, `libtapa`/`libfrt`, gflags/glog,
  nlohmann-json, tinyxml2, and yaml-cpp development dependencies. No AutoNTT
  performance claim or successful preloaded-adapter result is recorded.

The fully parallel N=16 timing diagnosis identified a 9.803 ns, 37-level data
path in the earlier 8 ns run. The old profile inserted delay registers after a
combinational product/reciprocal-product/quotient-product/correction expression.
The new `split-barrett` profile physically separates these operations across five
scheduled stages and is restricted to the custom fully parallel Barrett backend.
Routed improvement must be established by the two-point timing-repair campaign.
