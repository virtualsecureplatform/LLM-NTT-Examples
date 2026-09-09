# Timing and LLM acquisition fixes

HOGE forward and bidirectional YATA now pass the routed setup/hold checks under
the stated 4 ns out-of-context fabric contract. The LLM policy now uses measured
resource feasibility when choosing its next experiment. The
[final timing evidence](measured-evidence/timing-feedback/final-report.md)
retains the intermediate failures, matched synthesis comparisons, and artifact
integrity results. Fresh live LLM trials are running; their result is still pending.

## Final timing results

All measurements use U280 `xcu280-fsvh2892-2L-e` and Vivado 2023.2.

| Routed design | Setup slack ns | Hold slack ns | LUT | FF | DSP | Transaction cycles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HOGE forward, control-only reset plus output repair | 0.000 | 0.000 | 207144 | 259062 | 1024 | 202 |
| YATA 8×8, registered arithmetic and output converter | +0.067 | +0.010 | 52863 | 16882 | 80 | 513 |

Both use zero BRAM and URAM. HOGE has **no spare reported timing margin**.
Its [final timing report](measured-evidence/timing-feedback/hoge-final-timing.rpt)
and [route status](measured-evidence/timing-feedback/hoge-final-route-status.rpt)
show nonnegative setup/hold, all 397443 routable nets fully routed, and no routing
errors. The repaired checkpoint and all source/output integrity checks pass.

The contract uses `BUFGCE_X0Y0`, 0.5–1.0 ns input arrival and 0–1.0 ns output
requirements, referenced to `input_cycle_reg[0]/C` for HOGE and
`core/executing_reg/C` for YATA. All non-clock inputs, including reset, and all
outputs are constrained. Two preserved identity LUTs per non-clock input and
output provide internal physical paths; HOGE's final repair adds eleven more
output LUTs. Every buffer counts in utilization. No timing exception or changed
clock/I/O delay is used to promote a failed result.

This is a conditional neighboring-fabric model, not a board or shell result.
External port wiring has no fixed physical partition locations; the given
arrival/output-delay windows represent that integration boundary. Original
zero-delay synthesis remains separate. There is no matched extracted-HOGE or
extracted-YATA routed comparison here. See the [fabric contract](fabric-timing-contract.md).

## Generator and physical changes

HOGE's original path crossed factor lookup, multiplication, modular reduction,
the transpose, and the next radix level. The factor path now has nine registered
stages: captured inputs, four 32-bit partial products, product addition, and
Goldilocks reduction/correction. The radix implementation pipelines constant
modular shifts and butterflies with aligned valid/cycle tags.

NGen `e6bffa0` resets phase, validity and control state while allowing HOGE
arithmetic and transpose data-delay registers to update without reset. Clearing
valid stages discards pre-reset work; data becomes observable only after fresh
operands traverse the pipeline. This removes unnecessary reset fanout without
changing arithmetic or adding cycles. Other users of the transpose emitter keep
the original reset behavior by default.

YATA uses a real seven-stage arithmetic lane with dependent commit at cycle eight
and a four-stage output torus converter. The 8-, 64- and 512-point variants pass
their full arithmetic oracles. The 512-point inverse wait is 2609 cycles; its
watchdog was raised from 2000 to 4096 without weakening arithmetic comparisons.

The route history isolates the remaining physical failures:

| HOGE forward route attempt | Setup ns | Hold ns | Result |
| --- | ---: | ---: | --- |
| Registered arithmetic, output buffers | +0.280 | −0.680 | Direct-input hold failure |
| Added input buffers | −0.858 | +0.010 | Reset fanout to arithmetic data |
| Removed arithmetic-data reset | −0.427 | −0.020 | Reset fanout to transpose data |
| Removed transpose-data reset | 0.000 | −0.017 | Eleven output hold failures |
| Targeted output hold repair | 0.000 | 0.000 | Pass under the stated contract |

The reusable [output repair command](fabric-timing-contract.md#incremental-output-hold-repair)
opens a verified routed checkpoint, fixes existing cell placement, inserts
identity LUTs only at negative-hold outputs, and runs placement plus
`route_design -preserve`. The first attempt's DSP BEL-lock error remains a
failed record. The corrected flow keeps expanded DSP subcells site-fixed and
locks ordinary cell BELs. One pass inserts
[eleven output LUTs](measured-evidence/timing-feedback/output-hold-repairs.txt);
Vivado also replicates one control register. No transform cycles are added.

Matched final synthesis uses 206909 LUT / 259090 FF / 1024 DSP forward and
172490 LUT / 236444 FF / 512 DSP inverse. Both have +1.770 ns estimated setup
slack and −0.075 ns estimated hold slack. Inverse routing is not measured.
Forward/inverse transactions are 202/169 cycles, compared with the original
104/73. YATA's transaction grows from 86 to 513 cycles. The extracted HOGE
references still win the matched synthesis area/transaction comparison. These
fixes establish timing feasibility at substantial pipeline cost, not general
performance superiority.

## Resource-aware LLM acquisition

Framework `0a5912e` explicitly separates correctness, timing and resource
feasibility. Observations include exceeded resource limits and missing metrics.
Failed/incomplete measurements do not become zero-resource samples. The prompt
requests a small calibration anchor, then exploration using measured headroom,
objectives and remaining evaluation budget.

Advice uses only acquired observations from the matching architecture family.
It attempts the structural fit; when data is insufficient, labeled LUT/FF/DSP
replication heuristics supply advice. Predictions neither prune candidates nor
enter measured frontiers. Ranking has no hidden reference-pool lookup.

Sequential replay re-ranks after each acquired observation. The policy receives
copies of legal configurations and observed metrics; only the evaluator sees
unobserved outcomes and reference IDs. Tests cover hidden-data boundaries,
mutation, invalid choices, missing measurements and resource-limit failures.

The [N=128 replay](measured-evidence/timing-feedback/replay128.json) recovers 75%
of the four-design reference frontier in each of three repetitions, with three
feasible discoveries per trial. This matches enumeration and is the maximum
possible with three evaluations. The old clean live LLM study recovered 25%.
The [N=256 replay](measured-evidence/timing-feedback/replay256.json) recovers both
reference-frontier designs in three evaluations, also matching enumeration.

Fresh live confirmation uses nine evaluations: three repetitions of three
experiments, the original N=128 campaign and exactly the original generator
executable, in isolated framework `0a5912e` / NGen `997122d` checkouts. It starts
after all timing experiments terminate. Earlier replay is not substituted for
this hardware result. Zero-temperature repetitions are not independent random
seeds, and a finite-pool result does not establish general LLM superiority.

## Regression evidence and reproduction

NGen passes **159 Scala tests**; the framework passes **143 Python tests**.
Four-state transpose tests compare resettable and control-only-reset data delays
over 1200 cycles at widths 2, 8 and 32, including gaps and aborted frames.
Complete native and SGen-composed forward/inverse oracles pass; both overlap,
gap and reset checks pass 240 frames at interval 32
([functional evidence](measured-evidence/timing-feedback/control-reset-functional.json)).
YATA passes full size/direction checks and 26 mid-operation reset checks.

Seven previously measured generic designs regenerate byte-identical RTL and
cycle metadata, including the six N=128 policy configurations and qualified
16K/q54 architecture ([generic preservation](measured-evidence/timing-feedback/control-reset-generic-preservation.json)).
All three YATA sizes also remain byte-identical after HOGE's reset changes
([YATA preservation](measured-evidence/timing-feedback/control-reset-yata-preservation.json)).

Preset import accepts an omitted simulation clock name as the existing default
`clock`, preserving the saved record. Hardware targets must still match exactly,
including clock period and every physical I/O constraint. Live-study campaign
and generator-executable equality checks remain strict.

```sh
python3 scripts/summarize_ntt_evidence.py --index campaigns/timing-feedback-evidence.json --output-dir build/fresh-timing-snapshot
python3 scripts/replay_search_policies.py --report build/policy128-reference-current/report.json --campaign campaigns/live-policy128.json --output-dir build/fresh-feedback-replay --budget 3 --seeds 2 3 4 --sequential-llm
```

Published [machine-readable timing results](measured-evidence/timing-feedback/final-report.json)
retain source hashes and qualification decisions. Earlier synthesis, first-route,
reset-only and YATA-closure snapshots remain available in the same evidence
directory; the [previous milestone report](final-plan-results.md) is unchanged.
