# Completion audit

The objective remains the full generator/search plan. This checklist records
missing evidence; it does not narrow the objective to the implemented subset.

| Requirement | Current evidence | Remaining acceptance work |
| --- | --- | --- |
| Reproducible NGen search | Run/resume/report smoke checks; source/tool/binary manifests | Expand campaign evidence to HOGE forward/inverse and Kyber; include extracted baselines |
| Independent generic arithmetic | Direct-definition/convolution unit checks; streaming forward 16K/54-bit and inverse 64-bit RTL | Validate additional FHE matrix points and external generators against the same oracle |
| Permutation choice | Square NGen/SGen stream checks at five widths; composed YATA correctness | Rectangular, linear and memory permutation comparisons; measure full-design adapter cost |
| Architectural improvements | Buffered stage-group implementation, arithmetic tests, measured interval/latency tradeoffs | Matched resource/routing ablations; inspect scheduling hazards against actual RAM timing |
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
