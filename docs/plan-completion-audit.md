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
| Proteus | Experimental exact-field isolated generation and raw-memory oracle checker; N=256/q32 SDF compiles but fails frame 1 | Diagnose RTL/testbench mismatch, pass oracle validation, add normalized boundary and routed comparison |
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

## Experimental Proteus adapter

`prepare_proteus_baseline.py` binds the requested field and roots in an isolated
copy and records source/artifact hashes. `check_proteus_baseline.py` compiles the
raw memory interface and checks it against the independent oracle. The current
N=256/q32 SDF run (`build/proteus-sdf256-namespaced`) fails frame 1, address 0:
actual 0, expected 2002987292. The adapter is experimental; this run is not a
validated baseline or an eligible performance comparison. Its partial cycle
metrics must not be used as correctness evidence. A normalized streaming
interface and further diagnosis remain unfinished.
