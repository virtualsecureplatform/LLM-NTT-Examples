# Completion audit

The objective remains the full generator/search plan. This checklist records
missing evidence; it does not narrow the objective to the implemented subset.

| Requirement | Current evidence | Remaining acceptance work |
| --- | --- | --- |
| Reproducible NGen search | Run/resume/report checks, source/tool/binary manifests, exact oracle gates, fresh extracted Kyber/YATA/HOGE references | Finish preset hardware comparisons and audit evidence reuse |
| Independent generic arithmetic | All 18 FHE matrix points pass; ordinary search also passes 128K/q64 inverse using automatic Verilator selection | Wider external-generator coverage and FPGA fit remain separate |
| Permutation choice | Five square widths, 12 rectangular shapes, eight linear cases; SGen switch/stride composed YATA oracles and three-option synthesis complete | Broader full-design cases; all small YATA alternatives still fail setup |
| Architectural improvements | Seven-stage Montgomery, independent stage groups, compact address logic, Kyber normalization, shared YATA conversion; integrated NGen passes 148 Scala tests | Finish compact routed and Kyber matched hardware ablations; retain YATA timing failure |
| Multi-fidelity search | Functional gates, synthesis/route, constrained frontiers, serialized vendor jobs; bandwidth and issue-capacity bounds | Resource lower-bound pruning and remaining evidence/cache audit |
| Cost models | Nearest-neighbor and structural fits, five-point errors, held-out architecture, live N=128 observations | Wider independent validation and policy samples |
| LLM versus controls | Six-point replay and completed eight-evaluation live N=128 pilot; negative LLM outcomes retained | Wider equal-budget trials; one seed does not establish policy superiority |
| OpenNTT | Exact-field raw/normalized oracles, forward/inverse and memory options, 16K/q54 stream, matched timing-qualified N=256 route | Wider matched workloads and configuration sampling |
| Proteus | SDF forward/inverse and portable MDC forward/inverse 32/64-bit oracles; explicit ROM repair; matched timing-qualified N=256 route | Wider matched workload/configuration sampling; preserve modified-baseline label |
| Routed timing | All three N=256 designs pass under identical two-buffer fabric contract with setup/hold/full-route gates | Compact-address routed ablation and broader configurations |
| Paper comparison | Source-linked roadmap, reproducible matched three-generator routed report, resource/cycle tradeoffs and policy results | Consolidate remaining ablations and broader coverage; no board or universal superiority claim |
| Board execution | Deferred by the approved plan | Not required for the routed-RTL milestone |

Completion requires the missing evidence above. Any performance claim must name
the workload, interface, target, tool version, timing constraints, and evidence stage.

## Latest timing diagnosis

`build/u280-registered-contract` completed synthesis and route. Setup slack is
+1.035 ns; hold slack is −1.589 ns, so routing evidence remains failed. The
post-route detailed report `/tmp/ngen-hold-contract.rpt` identifies `reset` to
`core/pe_pipeline_0/out0_reg[10]/R`: input arrival 0.2 ns, clock insertion delay
1.821 ns, data-path delay 0.017 ns. This is a synchronous reset boundary path.
The next timing investigation must model the launch/capture clock relationship
and reset contract correctly, or improve the reset distribution implementation;
it must not waive the failure merely to populate the routed frontier.

All experiments launched for the OpenNTT comparison in this increment completed.
N=256/q32 and N=16K/q54 reports are in `build/comparison-openntt-ngen256` and
`build/comparison-openntt-ngen16k54`. Proteus integration and the other unmet
milestones above remain part of the active objective.

## Proteus adapter validation

The initial SDF failure was stale completion state: upstream validity shift
registers are not reset. A drain bound derived from N and configured stage
latencies now clears this state. The streaming adapter includes two frame
buffers, natural/spectral order conversion, and the drain counter in measured
RTL. Draining overlaps capture/output when possible; its remaining cost is
included in the measured transaction.

N=256/q32 SDF forward/inverse and MDC forward pass all eight raw-memory vectors
and the shared streaming suite (saturation, stalls, and mid-frame reset).
`build/comparison-threeway256/report.json` compares the passing forward SDF/MDC
configurations with NGen and both OpenNTT modes. MDC inverse fails the impulse
vector at frame 2, address 0, lane 1: actual 1870938527, expected 2103843552.
It remains ineligible pending diagnosis. No Proteus resource or route win is
claimed from simulation cycles.

## Follow-up hold diagnostic

Post-route `phys_opt_design -aggressive_hold_fix` followed by `route_design`
on a copy of the failed checkpoint leaves WHS at -1.589 ns. Vivado reports
unroutable boundary paths for which it cannot add routing detours. Reports are
under `build/hold-fix-diagnostic`. This run does not establish timing closure.
The next diagnostic uses an explicit fabric-clock reference for the module I/O
contract; changing a contract requires fresh implementation evidence before
any new result can enter the routed frontier.

The fabric-reference diagnostic (`set_input_delay`/`set_output_delay` relative
to `input_full_reg/C`) changes WNS to +0.779 ns and WHS to -0.082 ns. It still
fails; no checkpoint is promoted under the changed constraints. Remaining
boundary hold depends on the external launch/capture model and physical clock
skew. An integrated fabric harness or a justified shared interface contract,
followed by new implementation runs, is still needed for routed closure.

Proteus MDC N=256/q32 normalized-stream synthesis at 4 ns completed with 17,672
LUTs, 21,754 FFs, 64 DSPs, zero BRAM/URAM, and estimated WNS +1.454 ns. These
are synthesis estimates, not routed timing. `measure_external_ntt.py` and the
comparison importer now retain hash-checked implementation evidence alongside
the verified stream. The measurement is `build/proteus-mdc256-synthesis`.

The first matched NGen N=256/q32, PE=2, stage-groups=1 synthesis uses 5,216
LUTs, 1,688 FFs, 22 DSPs and four BRAM tiles, but WNS is -3.447 ns at 4 ns.
The critical path runs from `correction_product_1` through the final Montgomery
multiply/reduction and butterfly subtraction to `out1`, with 7.397 ns estimated
delay and 34 logic levels. This is an internal arithmetic setup failure, separate
from the small-design OOC hold issue. Increasing stage-group count alone cannot
resolve it. This identified the need to pipeline the arithmetic path, preserve valid/tag
alignment and stage-drain correctness, and correct latency metadata. The
implementation and matched checks are recorded below.

## Revised Montgomery arithmetic

The seven-stage radix-2 Montgomery pipeline is now implemented and independently
verified, including 64-bit inverse and 16K/54-bit forward transforms. The first
matched synthesis improves WNS from -3.447 ns to +0.582 ns at 4 ns. Its resource
and cycle tradeoffs, latency metadata correction, and evidence paths are in
[the pipeline comparison](montgomery-pipeline-comparison.md). The prior setup
failure is historical evidence for the change; routed closure remains open.

## Routed arithmetic and policy evaluation

The seven-stage NGen N=256/q32 implementation completed routing with WNS
+0.329 ns, WHS -0.080 ns, 4722 LUTs, 1742 FFs, 22 DSPs and four BRAM tiles.
It is excluded under the original zero-delay I/O contract. Fresh runs now use
[the shared fabric contract](fabric-timing-contract.md); no older run is promoted.

An equal-budget [policy replay](policy-replay.md) now saves acquisition traces,
frontier recovery, prediction errors, and live LLM requests/responses. The small
smoke pool gives no policy advantage. A larger resource-constrained measured
pool is running; end-to-end and held-out evaluation remain unfinished.

The isolated Proteus MDC inverse now has an explicit, provenance-recorded
[ROM alignment repair](proteus-inverse-repair.md). Modified 32-bit forward and
inverse streams and a 64-bit inverse stream pass independent functional checks.
The unbuffered fabric run still fails hold; the optional physical output-buffer
experiment described in the timing contract has passed synthesis, with routing
pending. Neither result establishes overall plan completion or a routed win.

Functional-only campaigns are now checked in for HOGE 1024 forward/inverse and
Kyber 256 (`campaigns/hoge-forward.json`, `hoge-inverse.json`, and `kyber.json`).
Their initial validation runs are in progress under `build/preset-*-validation`;
no pass is claimed until each report is inspected. Matched OpenNTT and modified
Proteus forward routing runs are queued under the buffered fabric contract.
The policy-pool driver failure and isolated retry are documented in the replay
notes. Per-job driver snapshots prevent later workspace edits from changing a
running measurement script.

The HOGE forward campaign passed microcoded indexed/switch and full-throughput
switch configurations. Stage-parallel indexed initially failed Verilator
elaboration (`BLKLOOPINIT` on the 1024-element nonblocking update loop), before
simulation. NGen now emits the identical register updates explicitly. Four
focused Scala tests and the fresh complete forward stream campaign
`build/hoge-stage-forward-explicit` pass. Inverse and Kyber campaigns are still
being checked; the initial tool failure is retained in the original report.

The structural resource model and one held-out architecture check are now
recorded in the policy replay notes. They improve estimates but do not provide
safe pruning bounds. OpenNTT's matched buffered fabric route completed with
10120 LUTs, 11088 FFs, 32 DSPs, three BRAM tiles, WNS +0.429 ns and WHS -0.019 ns
(`build/openntt256-buffered-fabric-route`). It remains excluded: the physical
buffer experiment has not established matched routed closure.

NGen now has a passing routed point at N=256/q32 under the buffered fabric
contract (WNS +0.299 ns, WHS +0.010 ns). The matched OpenNTT report retains its
hold failure; see the timing-contract document for resources and limitations.
Proteus and the missing policy-pool point are being retried after relocating
driver snapshots outside the build directory cleaned by the shell driver.
An end-to-end fake-vendor regression covers snapshot survival during cleanup.

HOGE stage-parallel inverse passes the repaired full stream test as well.
[Rectangular component validation](permutation-validation.md) now covers all
12 nonsquare 2/4/8/16 shapes under the memory adapter's serialized contract.
Linear permutations and full-design adapter measurements remain outstanding.

Kyber's initial preset run also encountered Verilator's nonblocking-array-loop
elaboration limit. Explicit reset/capture/commit assignments preserve its bank
transfer semantics. The focused Scala test and unchanged full preset evaluator
now pass in `build/kyber-explicit-validation`. Together with the HOGE forward
and inverse checks above, this supplies functional preset campaign evidence;
extracted baseline and hardware measurements remain separate acceptance work.

Fixed-width SGen stride component checks now pass eight single-/dual-RAM cases
with per-design `next` lead timing and independent matrix ordering. The new
bounded linear-permutation composition also passes the full YATA 8x8 transform
oracle. A three-option full-design permutation synthesis comparison is running;
see the permutation-validation document for contracts and remaining limitations.

The six-point measured policy pool is complete. Its equal-budget replay finds
both feasible designs with enumeration but none with LLM ranking at budget
three. All results, including this negative LLM result, are retained in the
policy-replay document; no default-policy superiority is inferred.


All three matched routed measurements are now imported in
`build/comparison-threeway256-buffered-route-complete`. NGen passes the timing
gates; OpenNTT and modified Proteus both have WHS -0.019 ns and remain excluded.
Detailed baseline hold reports are queued to guide a physical fix under the
unchanged contract. [Bandwidth constraints](bandwidth-constraints.md) now add
optimistic necessary-condition pruning and measured-rate eligibility without
promoting predictions to evidence. Resource-bound pruning and live acquisition
trials remain unfinished.

A [sequential policy runner](live-policy-trials.md) now chooses one legal
configuration, performs fresh oracle/synthesis evaluation, and then exposes
that observation to the next choice. Its N=128 campaign provides a held-out
workload execution pilot; measurements are pending. Component tests verify that
missing measurements never become zero-cost samples, and the ordinary CLI
rejects selections outside the legal campaign space.

The detailed baseline hold reports identify insufficient output-path delay after
one identity LUT. A common two-stage identity-LUT target is prepared for fresh
matched routing. The original one-stage failures remain unchanged evidence.


The committed sequential policy pilot is running at `build/live-policy128-trials`.
Fresh two-buffer routing is running under the common target for NGen, OpenNTT,
and Proteus. Executable inputs remain fixed while the live trial is active.
The full 18-point FHE correctness matrix (N=16K/64K/128K, q widths 32/54/64,
both directions) is also running with PE=2, radix=2, Montgomery, one stage group.
Campaigns and reports are under `build/fhe-matrix-single-pe2-campaigns` and
`build/fhe-matrix-single-pe2`. These launches do not establish passes or hardware
fit; each result still requires inspection.

Fresh [extracted preset comparisons](preset-baseline-comparison.md) now pass
Kyber, YATA, and both HOGE directions against unchanged tests. They retain slower
NGen points as well as faster cycle-count points without claiming achieved
hardware speedups. The full-design three-option permutation synthesis comparison
has finished; all three fail setup, and the stride adapter is more expensive
on this small task. An isolated Kyber normalization improvement removes 256
inverse cycles and passes the original oracle; integration and matched hardware
measurement remain pending while live trial inputs are fixed.

The [matched three-generator routed comparison](threeway-routed-comparison.md)
now passes for all three N=256/q32 streams under the shared two-buffer fabric
contract. NGen has the lowest LUT/FF/DSP cost; modified Proteus has the shortest
frame interval, and OpenNTT uses one less BRAM tile than NGen. This closes the
single-workload matched-route evidence gap, not the wider comparison scope.

The first N=128K/q32 forward matrix attempt compiled with Icarus but exhausted
its 1200-second evaluation budget during reset verification after eight main
frames. Both independent Verilator attempts (original RTL and externalized
control ROMs) ended with signal 9, before simulation. Neither is a correctness
pass. Control-ROM externalization passes an N=256 full-suite check and two
focused regressions, but does not yet solve large-design elaboration. A fresh
longer-budget Icarus recheck preserves the original attempts and full oracle.

[Resource-capacity pruning](resource-capacity-pruning.md) now rejects provably
impossible closed U280 cores using a prefix-state lower bound and a padded
resource-capacity upper bound. It requires all five resource caps and consumes
no evaluator budget. The 107-test Python suite passes. The integrated compact
N=256 design also passes matched routing; the resource tradeoff is recorded
in the compact-address document.

Kyber now has a pipelined setup-qualified implementation and a matched extracted/
pre-pipeline/pipeline synthesis comparison. It passes the unchanged arithmetic
oracle and a new reset-abort regression, but remains much larger than the
extracted reference. Routed Kyber hold, storage architecture, and wider baseline
and search-policy coverage remain open; these are not hidden by setup closure.

[Compact Kyber storage](kyber-banked-storage.md) now passes the original oracle,
reset recovery, a 16-operation bank-reuse check, and 4 ns synthesis. It uses
628 LUTs, 223 FFs, two DSPs and one BRAM tile at the extracted reference's 1414
transaction cycles, trading one extra DSP for fewer LUTs/FFs/BRAM. The opt-in
compact backend explicitly requires sequential full-frame load/compute/read
phases. Both backends are exposed by the Kyber campaign; the broad command
interface remains available through microcoded. Routed closure is still not
established for this preset.

The next wider matched hardware comparison uses
`campaigns/fhe16k54-two-buffer-fabric.json`: N=16384/q54 forward, four external
lanes, PE=2, and the same two-buffer fabric contract as the N=256 comparison.
NGen's run is `build/ngen-fhe16k54-two-buffer-fabric`; the already verified
OpenNTT stream is queued for implementation at
`build/openntt-fhe16k54-two-buffer-fabric`. These launches do not establish
resource fit or timing closure. The integrated Kyber work completes 149 Scala
and 111 Python tests, including both normal search backends and RAM reset checks.

## Hardware provenance and 16K measurement update

New hardware evidence hashes inputs before/after measurement and retains output
artifact hashes and original measured fields. Pareto selection and policy replay
reject changed evidence; historical records remain explicitly legacy-unverified.
See [hardware evidence integrity](hardware-evidence-integrity.md). All 113 Python
tests pass.

The matched N=16384/q54 NGen simulation passed. Synthesis completed at 114739 LUT,
2807 FF, 52 DSP, 48 BRAM and setup WNS -0.292 ns under the 4 ns target. This is a
setup failure, not a qualified 250 MHz result. Routing is still running; the
matched OpenNTT route follows in the serialized campaign. No routed conclusion
is available yet.

## Large PE control-ROM implementation

NGen `1382267` introduces synchronous prefetch for large static radix-2 control
ROMs, targeting the 16K design's distributed control-table area. Both 16K/q54
transform directions pass the full oracle with identical cycle metrics, and
all 150 Scala tests pass. Synthesis is queued; no area or timing win is claimed.
See [PE control-ROM prefetch](pe-control-rom-prefetch.md) for exact evidence and
the matched campaign. The wide Montgomery multiplier remains a separate timing
limitation, and the overall roadmap is still incomplete.
