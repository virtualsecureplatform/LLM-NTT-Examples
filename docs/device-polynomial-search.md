# Device-aware polynomial multiplication search

This first milestone searches the existing, qualified polynomial-product pool
under FPGA resources, timing, arithmetic error, and a modeled external-bandwidth
limit. It does not implement new hybrid engines, product-level sharing, HBM
controllers, or LLM proposals. Those remain subsequent generator milestones.

## Target and evidence

[u280-device.json](../studies/u280-device.json) selects
`xcu280-fsvh2892-2L-e`, Vivado 2023.2, and 250 MHz. Capacities were checked against
Vivado's part database. The default exploration budget is 80% of LUTs, FFs,
DSPs, BRAM36 equivalents, and URAMs. Override individual ceilings through
`resource_limits`. An 18 Kb RAM counts as half a BRAM36 equivalent.

The bandwidth default is an explicit **32 GB/s aggregate assumption**, not a
measured U280 HBM rate. Each product transfers A, B, and the result, with
byte-aligned coefficients. Twiddles and intermediate products remain on chip.
Steady-state throughput is capped by both `clock / measured product interval`
and `bandwidth / bytes per product`; it assumes transfer overlap. Cold latency
adds transfer time without overlap. Neither estimate is board execution time.

Vivado maps the unchanged qualified `SearchTop` RTL out of context. The clock
and maximum/minimum input/output delays are constrained, including reset.
The IO max-delay budget is 25% of a period; the minimum is zero. Mapping records
actual LUT/FF/DSP/BRAM/URAM use; routing records setup, hold, pulse-width slack,
constraint completeness, and DRC reports. This is not a placed board shell or
a bitstream qualification. Default implementation directives and the tool's
default seed are recorded; no unsupported placement-seed override is implied.

The initial real N=16 smoke run completed mapping and routing. It measured
5,851 routed LUTs, 2,480 FFs, 14 DSPs, and 6 BRAM36 equivalents. Setup slack
was -1.691 ns and hold slack -0.050 ns at the requested 250 MHz, so it was
correctly excluded from feasible results. Local reports and plots are in
`build/device-product-smoke/report/`. No successful timing result is implied.

Only a routed design with intact evidence, complete constraints, nonnegative
setup/hold/pulse-width slack, a valid DRC result, and measured resources inside
the budget is called feasible. Mapping success and model predictions never
establish timing feasibility. The AMD [timing-constraint guidance](https://docs.amd.com/r/2023.2-English/ug949-vivado-design-methodology/Checking-That-Your-Design-is-Properly-Constrained)
describes why unconstrained endpoints must be excluded.

## Run

Use the host Vivado installation, rather than the simulation container. The
source campaigns must retain their detailed qualification artifacts in `build/`.
The compact CSV snapshots alone are insufficient to promote historical RTL.

```bash
python3 scripts/device_polynomial_study.py \
  --campaign build/polynomial-study-512-optimized \
  --campaign build/polynomial-study-512-full-fft \
  --output-dir build/device-polynomial-512 --dry-run

python3 scripts/device_polynomial_study.py \
  --campaign build/polynomial-study-512-optimized \
  --campaign build/polynomial-study-512-full-fft \
  --output-dir build/device-polynomial-512 --policy model
```

The N=512 inventory contains 207 unique qualified products. The warmup comprises
12 calibration points (four backend families across three workloads) and six
held-out points. Calibration prefers exact, baseline radix-2 Barrett NTTs and
exact f30/g0 FFTs: two lanes for streamed/compact, four for stage-parallel and
full-throughput. Held-out cases prefer a four-lane/two-PE radix-8 streamed NTT
and a two-lane f32 full-throughput FFT with omission depth one. Fallbacks are
deterministic for smaller inventories. Warmup includes cases outside the selected
error limit to test the model; finalist selection always enforces the limit.

The default `--max-trials 24` counts all mapped attempts, including calibration,
held-out, failures, and timeouts. It then routes up to six finalists, distributing
attempts across workloads. If any workload still lacks a feasible design, the
runner can spend up to `--max-route-budget 12`. Candidates must first fit the
mapped resource budget. If no candidates qualify, reports explicitly retain
"no feasible design found within budget". Mapped and routed attempts are
separate expensive evaluations; default total cost is at most 36 invocations.
An error limit of zero selects exact products by default.

`--policy enumerate`, `random`, and `model` use the same warmup and budgets.
The model uses at most three same-backend calibration/search neighbors and
scales each measured resource category separately using generic structural
features. It is an empirical model, not a confidence bound. Held-out measurements
never train acquisition. Held-out absolute and relative prediction errors are
published; relative error is undefined when the actual count is zero.
The existing simulated cycles and generic counts are known for the entire pool:
this benchmark reduces **device implementation evaluations**, not the cost of
discovering the original RTL/correctness grid from scratch.

Specify `--seed`, `--error-limit`, `--timeout`, and `--threads` as needed.
The timeout applies per mapped/routed invocation and defaults to one hour;
the runner is serial with four Vivado threads. Failed or resource-infeasible
measurements remain charged to the budget.

## Resume and outputs

Repeat the same command with `--resume`. Resume verifies original campaign,
target, tool, search-policy, and implementation-code identities and all cached
evidence hashes. Timeout may change; target or budget changes need a new output
directory. A lock prevents two runners from mutating one campaign concurrently.
Original simulation campaigns and their evidence are never overwritten.
An interrupted trial is recovered from sealed stage evidence when available;
otherwise it is recorded as a failed, charged attempt after confirming that its
Vivado process is no longer alive. A still-running orphan trial blocks resume
instead of launching duplicate work. Interrupted elapsed time includes the gap
until recovery.

Each campaign writes:

- `manifest.json`: pool, tool, code, target, policy, and budget identities.
- `results.json`: active trial, completed attempts, predictions, held-out errors,
  routed-feasible designs, Pareto sets, and evaluation-count/wall-time history.
- `points.csv` and `summary.md`: measured resources and current outcomes.
- Per-stage TCL, utilization/timing/DRC reports, checkpoints, and hash seals.
- `exports/<point>/`: unchanged RTL, routed constraints, and an evidence manifest
  for each feasible product. Full checkpoints remain with the stage evidence.

The routed Pareto objectives are error bound, five FPGA resource categories,
kernel latency, and bandwidth-limited throughput, separated by workload.
Missing measurements are never replaced with zero for feasibility.

Generate SVG/PNG figures with the existing plotting environment:

```bash
build/polynomial-report-venv/bin/python scripts/plot_device_study.py \
  --campaign build/device-polynomial-512 --output-dir build/device-polynomial-512/plots
```

Repeat `--campaign` to compare model/random/enumeration runs. Comparisons require
identical pool, warmup, budgets, device, and error constraints; only policy and
search seed differ. The figures show routed-feasible results against both total
device evaluations and wall time, plus the resource/throughput tradeoff.

## Pipelined product comparison

The opt-in `product_profile: "pipelined"` preserves historical baseline RTL and
point identities. It adds registered constant-modulus reduction for input lift,
pointwise multiplication and CRT reconstruction, and banked frame storage with
one write per bank. The split FFT product uses separate operand banks and a
registered accumulator with synchronous memory reads. These changes trade
registers and additional latency for shorter arithmetic paths and inferable RAM.
They do not change the NGen butterfly pipeline itself.

`studies/torus512-pipelined-reductions.json` defines twelve exact candidates:
Barrett, Montgomery and Shoup streamed NTT products plus a full-throughput FFT,
for each of the three coefficient workloads. Montgomery uses NGen's existing
deeper pipeline. Every candidate must pass the full product correctness,
protocol, reset and interval checks before device evaluation.

```bash
scripts/run_polynomial_study.sh \
  --spec studies/torus512-pipelined-reductions.json \
  --output-dir build/polynomial-study-512-pipelined-reductions

python3 scripts/device_polynomial_study.py \
  --campaign build/polynomial-study-512-pipelined-reductions \
  --output-dir build/device-polynomial-512-pipelined \
  --max-trials 12 --route-budget 6 --max-route-budget 12
```

For incremental grids, `--reuse-from <results.json> --reuse-compatible-grid`
allows changes to grid axes while retaining matching qualified points. It still
checks workloads, arithmetic sources, generator/tool identities and artifact
hashes. The default reuse policy requires the same grid. New arithmetic or a
changed product profile requires fresh qualification.

Routing prioritizes workload coverage and then the smallest mapped setup
violation, before estimated throughput. Mapped slack guides selection only;
all routed feasibility requirements above remain mandatory.

## Find one option meeting 250 MHz

The focused target `studies/u280-kernel-harness.json` uses the same device,
250 MHz clock and resource ceilings, with `implementation_context` set to
`registered-harness-v2`. The default context remains the historical standalone
flow. The harness drives registered full32 × ternary operands, holds them under
backpressure, introduces registered sink stalls, and captures all output bits
in a registered signature. A BUFG (mapped to BUFGCE on this part) supplies the
implemented clock tree, including tool-inserted global buffering for high-fanout controls. Startup
reset is generated synchronously on chip. Only clock is exposed. The 64-bit
signature remains in preserved internal sink registers, so the full on-chip
source–kernel–sink circuit is timed without an unrelated external data interface.
There are no datapath false paths or multicycle timing exceptions.

Before mapping, the real kernel plus harness is simulated for three products
against the independent Python integer schoolbook oracle. Source beats, output
beats, stalled-output stability and the final signature are checked. Synthesis
and routing must retain the kernel hierarchy, source and sink registers, and
a single logical clock with buffered clock routing. Reports include the complete harness resource counts plus
hierarchical kernel utilization and clock utilization. This context measures
on-chip kernel integration; it does not qualify external board interfaces.

The fallback `product_profile: "registered"` inherits pipelined NTT arithmetic
and inserts elastic frame-output registers before pointwise and CRT
multiplication. Bank ownership can be released after copying the final beat
into the register; that beat remains stable during downstream stalls. Existing
profiles retain their generated RTL and point identities. The new profile is
restricted to NGen products.

Qualify the one fallback point, then run the bounded closure sequence:

```bash
scripts/run_polynomial_study.sh \
  --spec studies/torus512-timing-closure.json \
  --configuration-names full-ternary-460258af9afa6a1b \
  --output-dir build/polynomial-study-512-registered

python3 scripts/find_timing_met.py --output-dir build/timing-closure-512

build/polynomial-report-venv/bin/python scripts/plot_timing_closure.py \
  --campaign build/timing-closure-512
```

The runner starts with the qualified streamed Montgomery full×ternary product
(two lanes, one PE, radix 2). It stops at the first fully feasible routed result.
If the original product fails only hold, it tries post-route hold repair. It
then falls back to registered frame outputs, followed by hold repair or Explore
placement/routing with hold repair as appropriate. There are at most two design
mappings and four routing attempts, with a one-hour timeout per invocation and
four Vivado threads. Implementation recipes are recorded separately; checkpoints
can be reused across recipes only when the remaining target and tool identities
match. `--initial-campaign` can adopt a completed and verified first harness run.
Repeated commands reuse sealed attempts; changed manifests and unsealed
interrupted implementation attempts are rejected.

The output contains `attempts.csv`, `summary.md`, `results.json`, timing/resource
figures, and an exported winning kernel, harness, constraints, checkpoint and
reports with a hash manifest. Setup, hold and pulse-width slack must all be
nonnegative, constraints complete, DRC acceptable and resources within budget.
A positive setup result alone is not called timing-qualified. Kernel cycle
measurements come from the full qualification run; harness stalls are not a
throughput benchmark.

The earlier `registered-harness-v1` context exposed the signature as an external
data port. Its input-clock-referenced output timing includes an external
interface requirement; its measurements remain separate from v2. The v2 clock
probe reopens a candidate checkpoint and verifies every global buffer output
net has Vivado `ROUTE_STATUS=ROUTED` before declaring success.

AMD's [OOC clock-buffer guidance](https://docs.amd.com/r/2022.1-English/ug905-vivado-hierarchical-design/I/O-and-Clock-Buffers)
distinguishes internal BUFG routing from estimates for a buffer outside the
OOC module. This harness contains its global buffer; the clock-net probe checks
the implemented global routes. Clock-input placement and board clock delivery
remain outside the on-chip qualification scope.

The completed [N512 250 MHz result](results/timing-closure-512.md) includes the
measured timing/resource table, plot, provenance snapshot and diagnostic costs.

## Extend the timing-qualified Pareto frontier

The first extension holds the workload and implementation context fixed: exact
N=512 full32 × ternary negacyclic products modulo 2^32, the v2 on-chip harness,
U280, 250 MHz and the same resource budgets. It imports the passing pipelined
Montgomery point, and evaluates registered Montgomery products with two/four
internal lanes and one/two PEs. The external stream remains two coefficients
per beat. Other coefficient workloads need separate frontiers.

After completing the first timing-closure milestone, qualify the three new
architectures; the registered two-lane/one-PE product is already qualified:

```bash
scripts/run_polynomial_study.sh --spec studies/torus512-pareto250.json \
  --configuration-names full-ternary-9dc15b43d2f6268c \
    full-ternary-35d3fad46ca22405 full-ternary-c935c41fc882a79e \
  --output-dir build/polynomial-study-512-pareto250

python3 scripts/extend_timing_frontier.py \
  --campaign build/polynomial-study-512-pipelined-reductions \
  --campaign build/polynomial-study-512-registered \
  --campaign build/polynomial-study-512-pareto250 \
  --output-dir build/device-pareto250-512

build/polynomial-report-venv/bin/python scripts/plot_routed_frontier.py \
  --campaign build/device-pareto250-512
```

The extension imports the original measured point without another P&R run.
Each of the four new products gets one mapping and default routing attempt;
up to two timing-failing products can receive hold repair or Explore routing.
These are four new mapped attempts and at most six new routed attempts. Each
invocation uses four threads and a one-hour timeout. Failed and interrupted
attempts stay charged. Repeating an unchanged command reuses sealed stages
and preserves the original progress timestamps. Changed targets, source pools,
tools or runner code require a new output directory.

Every admitted point must pass full arithmetic qualification, resource budgets,
complete routed timing and DRC, and the clock-net probe. Explicit zero failing
setup/hold/pulse-width endpoint counts are required, including when reported
slack rounds to zero. Repair recipes can differ, but all remaining device,
clock, workload and harness constraints must match. No timing-failing point is
promoted based on its cycle count or predicted frequency.

The full Pareto set minimizes error, five measured resource categories and
kernel latency, and maximizes bandwidth-limited modeled throughput. Only
feasible products participate. CSV tables retain pending, failed and dominated
products with their status. The plot marks the complete frontier on LUT and DSP
projections; membership in the full set does not imply a two-objective frontier
in either projection. Throughput is modeled from the independently qualified
kernel interval at the fixed clock; harness traffic is not a throughput test.

Outputs include points.csv, results.json, summary.md, per-stage evidence and
clock probes, plus hash-manifested exports of every feasible product. The
original passing point and original result snapshots remain unchanged.

After the extension finishes, publish verified compact table/plot snapshots:

```bash
python3 scripts/report_routed_frontier.py --campaign build/device-pareto250-512
```

This rechecks routed evidence, endpoint failures, clock-probe hashes and Pareto
membership before saving `docs/results/pareto250-512.*`. Pareto membership is
computed within the five-design measured pool. The snapshot preserves rejected
points and the implementation budget as well as the achieved frontier.

The completed [five-point 250 MHz frontier](results/pareto250-512.md) reports
all four new designs passing default P&R, the measured resource tradeoffs,
clock/endpoint verification, and the full provenance snapshot.
