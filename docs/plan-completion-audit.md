# Completion audit

The objective remains the full generator/search plan. This checklist records
missing evidence; it does not narrow the objective to the implemented subset.

| Requirement | Current evidence | Remaining acceptance work |
| --- | --- | --- |
| Reproducible NGen search | Run/resume/report smoke checks; source/tool/binary manifests | Expand campaign evidence to HOGE forward/inverse and Kyber; include extracted baselines |
| Independent generic arithmetic | Direct-definition/convolution unit checks; streaming forward 16K/54-bit and inverse 64-bit RTL | Validate additional FHE matrix points and external generators against the same oracle |
| Permutation choice | Square NGen/SGen stream checks at five widths; composed YATA correctness | Rectangular, linear and memory permutation comparisons; measure full-design adapter cost |
| Architectural improvements | Buffered stage groups and seven-stage Montgomery pipeline; matched resource/setup ablation and oracle checks | Matched routed ablations; wider scheduling/RAM timing coverage |
| Multi-fidelity search | Functional gates, synthesis/route stages, resource-constrained frontiers, per-user vendor lock | Measured acquisition-policy comparison and resource/bandwidth pruning with validated bounds |
| Cost models | Nearest-neighbor fitting and leave-one-out machinery | Sufficient independent samples, error results, and held-out policy evaluation |
| LLM versus controls | Live legal-ID ranking, saved response, four passing candidates | Equal-budget trials against enumeration/random/cost with measured search outcomes |
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
