# Polynomial multiplication studies

## Bounded demonstration

The checked-in [demo specification](../studies/torus-demo.json) searches 12
configurations at N=32 for full signed 32-bit operands modulo `2^32`:
four streamed NTT architectures (one/two PEs and Barrett/Shoup reduction),
six FFT arithmetic configurations (24/30 fractional bits and omission depths
zero/one/two), and one four-bit output-rounding variant per backend.
The FFT rounding variant depends on the lowest certified exact FFT precision.
The shared NTT baseline is counted once. All 12 requested combinations are
supported by the backend rules; certification and hardware checks still decide
which qualify. The demo retains the full 101-frame correctness corpus,
12-frame timing run, protocol tests, certificates, and synthesis checks.

```bash
python3 scripts/polynomial_study.py --spec studies/torus-demo.json --dry-run
scripts/run_polynomial_study.sh --spec studies/torus-demo.json \
  --output-dir build/polynomial-study-demo
scripts/run_polynomial_study.sh --spec studies/torus-demo.json \
  --output-dir build/polynomial-study-demo --resume
```

Toolchain preparation is described below. Read `summary.md` for the comparison
and frontiers, `all-points.csv` for configuration/objective pairs, and
`results.json` for qualification evidence and explicit failures. The demo's
error views are exact, eight units (four-bit rounding), 7,200 units (omission
depth one), and 237,600 units (depth two). These are polynomial arithmetic
bounds, not FHE decryption guarantees. N=32 demonstrates the workflow;
its resource and cycle measurements do not predict N=512 performance.

The first pinned-toolchain demo run completed all 12 configurations in about
10.6 minutes on the development host, including generation, simulation, and
synthesis. All passed; three configurations remained on the exact frontier
and five on the unrestricted error frontier. This is a measured example,
not a runtime guarantee for another host.

For a later LLM search, keep this workload, candidate pool, validation pipeline,
and objectives fixed. Use the completed grid as the reference, then compare
the LLM's best qualified results and frontier coverage after a fixed number
of proposed trials. Count rejected, failed, and timed-out proposals in that
budget, including prerequisite evaluations for dependent rounding candidates;
report wall time separately from trial count. Compare against a
seeded random search with the same budget. Hide measurements for unevaluated
candidates from the LLM to avoid revealing the reference answers. The current
runner supplies the grid and evidence; an LLM proposal policy is future work.

## Full N=512 reference grid

The original reference grid fixes FFT architecture to compact, two lanes, and
zero guard bits while sweeping NTT architectures. The
[full-throughput FFT extension](../studies/torus512-full-fft.json) adds 36 FFT
configurations: full-throughput at two/four lanes, fractional precision 30/32,
and omission depths zero/one/two, across all three operand workloads. Three
NTT baselines also run to check agreement with the original campaign. This
extension fixes guard bits at zero and does not add output-rounding variants.
The runner now exposes `sgen_axes` (`sgen_backends`, `lanes`, `guard_bits`),
and dependent rounding, when requested, preserves backend, lanes, and guard
bits when selecting the lowest certified exact precision. Full-throughput
candidate generation is enabled through N=512; N=1024 remains outside that
qualification scope.

Qualify one exact full-throughput configuration first, then import its verified
evidence into the full extension with the same specification:

```bash
scripts/run_polynomial_study.sh --spec studies/torus512-full-fft.json \
  --output-dir build/polynomial-study-512-full-fft-qualification \
  --configuration-names full-full-ddcf2ae56dd04ce0
scripts/run_polynomial_study.sh --spec studies/torus512-full-fft.json \
  --output-dir build/polynomial-study-512-full-fft \
  --reuse-from build/polynomial-study-512-full-fft-qualification/results.json
```

The campaigns remain separate so the original evidence is preserved. Merge
their report snapshots with repeated `--campaign` arguments below. The report
checks corpus and workload identity, deduplicates repeated NTT baselines, and
recomputes Pareto membership over the union of qualified configurations.

The study compares complete negacyclic products modulo `2^32` with fresh
operands and the same two-coefficient ready/valid interface. The checked-in
[specification](../studies/torus512.json) distinguishes full signed 32-bit ×
full signed 32-bit, full × signed byte, and full × ternary multiplication.
Input ranges include `-2^31`, unlike the historical near-full-range sweep.

The arithmetic stage compares a streamed two-lane, one-PE radix-2 Barrett NTT
against compact two-lane FFT at seven fractional precisions. Each FFT precision
also tests omission depths zero, one, and two. Certification must establish
exact rounding of every included leaf product before hardware qualification.
Omission is the source of arithmetic error for certified FFT points.

The architecture stage crosses streamed/stage-parallel NTT backends, two/four
lanes, one/two PEs, radix 2/4/8, one/two stage groups, and three reductions.
Backend legality determines support; rejected Cartesian combinations stay in
the inventory. The shared arithmetic baseline is evaluated once. Profiles and
transpose boundaries remain fixed at baseline/indexed. FFT arithmetic points
provide the certified precision comparison alongside this NTT architecture sweep.

Output rounding by four/eight bits is tested on the NTT arithmetic baseline and
the lowest **certified** exact FFT precision for each workload. Its rounding
bound is eight/128 torus units. A certified FFT baseline may be selected even
if its simulation or synthesis failed; the rounding variant receives its own
complete checks. Omission and rounding are never combined. This separates
arithmetic work reduction from output rounding overhead.

## Run

From the repository root, enumerate without generators or synthesis tools:

```bash
python3 scripts/polynomial_study.py --dry-run > /tmp/torus512-grid.json
```

Prepare the pinned runtime as for the existing SGen precision campaign:

```bash
scripts/build_generators.sh
scripts/build_assurance_yosys.sh
scripts/build_fhe512_image.sh --output build/fhe512-sgen-precision.sif
scripts/run_polynomial_study.sh --output-dir build/polynomial-study-512
scripts/run_polynomial_study.sh --output-dir build/polynomial-study-512 --resume
```

Native execution is also supported with the pinned tools on `PATH`:

```bash
PATH="$PWD/build/tools/bin:$PATH" python3 scripts/polynomial_study.py \
  --output-dir build/polynomial-study-512
```

The specification exposes operand ranges, N, FFT precision, omission and rounding
lists, error views, and `ngen_axes` for the NTT architecture grid.
Use `--spec <json>` for a new workload study and `--timeout <seconds>` to change
the default 1,800-second limit per invocation. The runner evaluates one point at a time. For N>=512 FFT products, it compiles
one simulator with `-O3`, then checks the complete 101-frame corpus in four-frame
shards using up to 16 simulator processes. Set `--fft-workers` (1..32) and
`--fft-shard-size` (1..12) to change those limits. Each stage has one wall-time
budget including queued shards; a failed stage prevents all subsequent checks. `--configuration-names` selects IDs from the dry-run inventory;
unselected points remain visible. When selecting dependent FFT rounding points,
include the workload's exact FFT precision candidates as well.

Use the bounded demo above before an expensive full N=512 campaign.

## Evidence and interpretation

The completed campaign's [tables and tradeoff plots](results/polynomial-results.md)
are checked in with compact CSV snapshots and source fingerprints. Export tables
from the local evidence and regenerate SVG/PNG plots from those CSVs:

```bash
python3 scripts/report_polynomial_study.py \
  --campaign build/polynomial-study-512-optimized \
  --campaign build/polynomial-study-512-full-fft \
  --campaign build/polynomial-study-demo --output-dir docs/results
python3 -m venv build/polynomial-report-venv
build/polynomial-report-venv/bin/python -m pip install -r scripts/polynomial-report-requirements.txt
build/polynomial-report-venv/bin/python scripts/plot_polynomial_study.py
```

Each workload uses 36 structured frames, 64 seeded random frames, and a
wraparound impulse. Width-asymmetric products are regenerated with operands
swapped and checked against the swapped contract. Timing uses a separate
12-frame uninterrupted run. Protocol checks exercise input bubbles, output backpressure, and reset.
FFT protocol shards retain all original 64 bubble-frame inputs and the original
first eight inputs for each stalled/reset pass. Each reset shard uses one
uninterrupted frame to prime capture cancellation, avoiding an unnecessary
repeat of the full correctness corpus. Timing remains one uninterrupted
12-frame run; shard timings do not establish the frame interval.
All approximate outputs are checked against independent integer oracles;
error statistics compare those checked outputs with exact schoolbook products.
Observed bounds remain empirical; certificates and conservative arithmetic
bounds provide the qualification argument.

`results.json` retains certificates, complete configuration/contract identity,
stage evidence, artifact hashes, coverage, and per-workload frontiers.
`all-points.csv` exposes the configuration axes and measured objectives;
`summary.md` shows completion and the comparison table. Exact-parent differences
in JSON show whether omission or rounding changed resource counts or cycles.
The seven frontier objectives are analytical error bound, generic cells,
memory bits, register bits, multiplier operators, latency, and product interval.
Views include exact-only and limits of 8, 115,200, 3,801,600, and 4,000,000 units.
Ties remain visible. Failed/rejected points never enter a measured frontier.

Resume verifies the spec, source/tool/generator identities, and successful-point
artifact hashes. Failed, timed-out, and rejected points are retried. Successful correctness
shards can be reused only when their compiled binary, corpus, pass settings,
and input/test artifacts still match. Changing
execution timeout is allowed; changing the study requires a new directory.
The full campaign may take substantial time, especially the serial FFT corpus
and stage-parallel NTT synthesis. Reports keep incomplete coverage explicit.

The synthesis pass retains inferred memories and is identical across backends.
Cells are coarse Yosys operators, not FPGA LUTs. Throughput uses cycles, without
an assumed clock. This study measures polynomial multiplication; its error
limits do not establish an FHE operation's decryption reliability.

## Upgrade an existing campaign's evaluator

Keep the earlier campaign directory intact. After evaluator changes, use a new
output directory and import verified successful points:

```bash
scripts/run_polynomial_study.sh --output-dir build/polynomial-study-512-optimized \
  --reuse-from build/polynomial-study-512/results.json
scripts/run_polynomial_study.sh --output-dir build/polynomial-study-512-optimized --resume
```

Import requires matching workload specification, corpus, tools, generator
assemblies, runtime image, and arithmetic/generator sources. Only the study
runner and simulator evaluation sources may differ. Every reused point retains
its original evidence directory and source manifest/results hashes; old failures
are retried. Selection may expand from a qualification subset to the full
identical specification; each imported point still requires matching requested
configuration, contract, and artifact hashes. No previous results or RTL are overwritten.

The paired compiler benchmark accepts an existing qualified point and uses the
same complete-product RTL and seeded random frame for `-Os` and `-O3`:

```bash
python3 scripts/benchmark_product_simulation.py \
  --campaign-dir build/polynomial-study-512 \
  --configuration-name full-full-38058e160e6b49c5 \
  --output-dir build/polynomial-study-512-simulator-benchmark
```

Run it in the pinned runtime or with the pinned native tools on `PATH`.
`benchmark.json` records the input/RTL hashes, builds, simulator timings, and
measured speedup. This is software simulation performance, not hardware clock
frequency or product throughput.
