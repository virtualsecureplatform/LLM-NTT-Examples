# Completion audit

The objective remains the full generator/search plan. This checklist records
missing evidence; it does not narrow the objective to the implemented subset.

| Requirement | Current evidence | Remaining acceptance work |
| --- | --- | --- |
| Reproducible NGen search | Run/resume/report checks; source/tool/binary manifests; HOGE forward/inverse and Kyber functional campaigns | Include extracted preset baselines and hardware comparisons |
| Independent generic arithmetic | Direct-definition/convolution unit checks; streaming forward 16K/54-bit and inverse 64-bit RTL | Validate additional FHE matrix points and external generators against the same oracle |
| Permutation choice | Square streams at five widths; 12 rectangular memory shapes; eight linear/stride cases; switch and stride composition pass YATA | Finish matched full-design permutation synthesis and adapter-cost comparison |
| Architectural improvements | Buffered stage groups and seven-stage Montgomery pipeline; matched resource/setup ablation and oracle checks | Matched routed ablations; wider scheduling/RAM timing coverage |
| Multi-fidelity search | Functional gates, synthesis/route stages, constrained frontiers, per-user vendor lock; measured finite-pool replay and optimistic bandwidth/issue pruning | Resource-cost lower bounds and live end-to-end acquisition-policy trials |
| Cost models | Nearest-neighbor and structural fits; five-point errors and one held-out architecture | Larger independent samples and held-out workload/policy evaluation |
| LLM versus controls | Live legal-ID ranking, saved requests/responses; six-point equal-budget replay including negative LLM outcome | End-to-end trials and held-out workloads |
| OpenNTT | Exact-field isolated generation; independent forward/inverse and MemOpt N=256/q32 checks; normalized streaming checks including N=16K/q54; matched N=256/q32 and N=16K/q54 simulation comparisons | Routed/resource measurements and wider configuration sampling |
| Proteus | Exact-field isolated generation; N=256/q32 SDF forward/inverse and MDC forward pass raw and normalized streaming oracle checks; matched three-generator cycle comparison | Diagnose MDC inverse failure, expand workload coverage, routed/resource comparison |
| Routed timing | Actual checkpoint/report ingestion; failed hold excluded | Hold traced to zero-delay input boundary and unset clock source; explicit shared I/O/clock constraints added. First explicit-contract route still fails hold (−1.589 ns); diagnose clock insertion/interface model, then verify closure and measure candidates/baselines |
| Paper comparison | Source-linked roadmap | Matched reproducible comparison report; distinguish reproduced measurements from published numbers |
| Board execution | Deferred by the approved plan | Not required for the routed-RTL milestone; do not claim board results |

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
