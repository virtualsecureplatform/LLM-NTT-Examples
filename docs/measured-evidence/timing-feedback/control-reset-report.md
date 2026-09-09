# NTT generator evidence snapshot

Snapshot of named comparisons, not certification that the full project plan is complete. Legacy hardware evidence remains explicitly unverified by newer manifests.

Synthesis qualification requires completed implementation and nonnegative setup slack; it does not establish routed timing closure. Route qualification additionally requires nonnegative hold slack and completed routing. Rates at synthesis are estimates under the stated target clock.

## HOGE forward pipeline ablation

Matched workload and synthesis target. Preserves intermediate failures. Positive synthesis setup slack does not establish routed closure; transaction latency and area tradeoffs remain.

Workload: `{"kind": "preset", "task": "hoge_streaming_ntt_1024_p64"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **synthesis**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/hoge-forward-final-timing-comparison`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1fcbad1aa584 | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | True | 206909 | 259090 | 1024 | 0 | 1.77 | -0.075 | verified |
| 2cb48775dc22 | {"backend": "full-throughput", "generator": "ngen-sgen", "profile": "baseline", "transpose": "switch"} | True | False | 214565 | 45852 | 2304 | 0 | -8.332 | -0.029 | verified |
| 35d81fa5dd3e | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 176563 | 103519 | 1024 | 0 | -1.92 | -0.029 | verified |
| 5650fadf1c39 | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 177390 | 47528 | 1024 | 0 | -8.937 | -0.029 | verified |
| 92a70b187a4e | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | True | 209171 | 273241 | 1024 | 0 | 1.77 | -0.075 | verified |
| b445b73a4bfa | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | True | 210715 | 273392 | 1024 | 0 | 1.77 | -0.075 | verified |
| e0cac26420eb | {"generator": "extracted-rtl", "task": "hoge_streaming_ntt_1024_p64"} | True | True | 90300 | 194109 | 512 | 0 | 1.519 | 0.014 | verified |
| f62a296346de | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 214565 | 45852 | 2304 | 0 | -8.332 | -0.029 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 1fcbad1aa584 | 202 | not measured | 808.0 | not measured |
| 2cb48775dc22 | 104 | not measured | unqualified | not measured |
| 35d81fa5dd3e | 122 | not measured | unqualified | not measured |
| 5650fadf1c39 | 104 | not measured | unqualified | not measured |
| 92a70b187a4e | 202 | not measured | 808.0 | not measured |
| b445b73a4bfa | 202 | not measured | 808.0 | not measured |
| e0cac26420eb | 170 | not measured | 680.0 | not measured |
| f62a296346de | 104 | not measured | unqualified | not measured |

Qualified frontier: e0cac26420eb.

## HOGE inverse pipeline ablation

Matched workload and synthesis target. Preserves intermediate failures. Positive synthesis setup slack does not establish routed closure; transaction latency and area tradeoffs remain.

Workload: `{"kind": "preset", "task": "hoge_streaming_intt_1024_p64"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **synthesis**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/hoge-inverse-arithmetic-reset-comparison`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 23d403be916a | {"generator": "extracted-rtl", "task": "hoge_streaming_intt_1024_p64"} | True | True | 140242 | 239475 | 512 | 0 | 1.518 | -0.075 | verified |
| 2a0d2b6508d1 | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 135711 | 62058 | 512 | 0 | -3.838 | -0.029 | verified |
| 3bbc74c500dd | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | True | 174396 | 243609 | 512 | 0 | 1.77 | -0.112 | verified |
| 712946530a20 | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | True | 171422 | 241803 | 512 | 0 | 1.77 | -0.112 | verified |
| a410fc119fbc | {"backend": "stage-parallel", "generator": "ngen", "profile": "baseline", "transpose": "indexed"} | True | False | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | verified |
| aedcad880dd6 | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 136166 | 34058 | 512 | 0 | -9.844 | -0.029 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 23d403be916a | 129 | not measured | 516.0 | not measured |
| 2a0d2b6508d1 | 82 | not measured | unqualified | not measured |
| 3bbc74c500dd | 169 | not measured | 676.0 | not measured |
| 712946530a20 | 169 | not measured | 676.0 | not measured |
| a410fc119fbc | 69 | not measured | unqualified | not measured |
| aedcad880dd6 | 73 | not measured | unqualified | not measured |

Qualified frontier: 23d403be916a.

## YATA arithmetic and output pipeline ablation

Matched workload and synthesis target. Preserves intermediate failures. Positive synthesis setup slack does not establish routed closure; transaction latency and area tradeoffs remain.

Workload: `{"kind": "preset", "task": "small_yata8x8_raintt_p27"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **synthesis**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/yata8x8-timing-fix-comparison`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 152a494e0ad1 | {"backend": "microcoded", "generator": "ngen", "profile": "f300", "transpose": "switch"} | True | False | 49713 | 16020 | 80 | 0 | -1.574 | -0.029 | verified |
| 5049111e3b76 | {"backend": "microcoded", "generator": "ngen-sgen-linear", "profile": "baseline", "transpose": "switch"} | True | False | 58769 | 11306 | 424 | 8 | -5.483 | -0.075 | legacy-unverified |
| 7f19e997defb | {"backend": "microcoded", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 58565 | 9823 | 424 | 0 | -5.483 | -0.042 | legacy-unverified |
| 818225ba7242 | {"backend": "microcoded", "generator": "ngen-sgen", "profile": "baseline", "transpose": "switch"} | True | False | 58565 | 9823 | 424 | 0 | -5.483 | -0.042 | legacy-unverified |
| d3ae87212810 | {"backend": "microcoded", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 51489 | 9774 | 88 | 0 | -5.805 | -0.042 | legacy-unverified |
| ecc815f2608a | {"backend": "microcoded", "generator": "ngen", "profile": "f300", "transpose": "switch"} | True | True | 52340 | 16403 | 80 | 0 | 1.282 | -0.042 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 152a494e0ad1 | 513 | not measured | unqualified | not measured |
| 5049111e3b76 | 96 | not measured | unqualified | not measured |
| 7f19e997defb | 86 | not measured | unqualified | not measured |
| 818225ba7242 | 86 | not measured | unqualified | not measured |
| d3ae87212810 | 86 | not measured | unqualified | not measured |
| ecc815f2608a | 513 | not measured | 2052.0 | not measured |

Qualified frontier: ecc815f2608a.

## HOGE forward first route (hold failure)

Completed routing and positive setup, but negative hold. Conditional neighboring-fabric contract; no board timing or matched reference route claim. The prior exact-RTL arithmetic oracle is reused without changing its target.

Workload: `{"kind": "preset", "task": "hoge_streaming_ntt_1024_p64"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "clock_source": "BUFGCE_X0Y0", "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "input_cycle_reg[0]/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/hoge-radix-pipeline-forward-route-evidence`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 92a70b187a4e | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 211201 | 273327 | 1024 | 0 | 0.28 | -0.68 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 92a70b187a4e | 202 | not measured | unqualified | not measured |

Qualified frontier: none.

## YATA first route (hold failure)

Completed routing and positive setup, but negative hold. Conditional neighboring-fabric contract; no board timing or matched reference route claim. The prior exact-RTL arithmetic oracle is reused without changing its target.

Workload: `{"kind": "preset", "task": "small_yata8x8_raintt_p27"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "clock_source": "BUFGCE_X0Y0", "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "core/executing_reg/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/yata8x8-output-pipeline-route-evidence`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ecc815f2608a | {"backend": "microcoded", "generator": "ngen", "profile": "f300", "transpose": "switch"} | True | False | 52252 | 16804 | 80 | 0 | 0.149 | -0.02 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| ecc815f2608a | 513 | not measured | unqualified | not measured |

Qualified frontier: none.

## HOGE input buffering before reset correction

Same 4 ns conditional neighboring-fabric I/O window; two physical identity LUT stages per input and output. Full arithmetic oracle reused for identical RTL. No board or extracted-reference route claim.

Workload: `{"kind": "preset", "task": "hoge_streaming_ntt_1024_p64"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "clock_source": "BUFGCE_X0Y0", "input_hold_buffer_stages": 2, "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "input_cycle_reg[0]/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/hoge-radix-pipeline-forward-input-route-evidence`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 92a70b187a4e | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 214738 | 273312 | 1024 | 0 | -0.858 | 0.01 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 92a70b187a4e | 202 | not measured | unqualified | not measured |

Qualified frontier: none.

## YATA with repaired input boundaries

Same 4 ns conditional neighboring-fabric I/O window; two physical identity LUT stages per input and output. Full arithmetic oracle reused for identical RTL. No board or extracted-reference route claim.

Workload: `{"kind": "preset", "task": "small_yata8x8_raintt_p27"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "clock_source": "BUFGCE_X0Y0", "input_hold_buffer_stages": 2, "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "core/executing_reg/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/yata8x8-output-pipeline-input-route-evidence`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ecc815f2608a | {"backend": "microcoded", "generator": "ngen", "profile": "f300", "transpose": "switch"} | True | True | 52863 | 16882 | 80 | 0 | 0.067 | 0.01 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| ecc815f2608a | 513 | not measured | 2052.0 | not measured |

Qualified frontier: ecc815f2608a.

## HOGE arithmetic-only reset correction before transpose correction

Retained setup and hold failure. Worst setup path still runs from reset to transpose data registers; same conditional fabric window and physical input/output buffers.

Workload: `{"kind": "preset", "task": "hoge_streaming_ntt_1024_p64"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "clock_source": "BUFGCE_X0Y0", "input_hold_buffer_stages": 2, "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "input_cycle_reg[0]/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/hoge-valid-reset-forward-route-evidence`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| b445b73a4bfa | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 215952 | 273472 | 1024 | 0 | -0.427 | -0.02 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| b445b73a4bfa | 202 | not measured | unqualified | not measured |

Qualified frontier: none.

## HOGE control-only reset before output hold repair

Setup meets 4 ns at 0.000 ns slack; eleven output hold failures remain, worst -0.017 ns. Original failed route retained.

Workload: `{"kind": "preset", "task": "hoge_streaming_ntt_1024_p64"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "clock_source": "BUFGCE_X0Y0", "input_hold_buffer_stages": 2, "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "input_cycle_reg[0]/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/hoge-control-reset-forward-route-evidence`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1fcbad1aa584 | {"backend": "full-throughput", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 207133 | 259061 | 1024 | 0 | 0 | -0.017 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 1fcbad1aa584 | 202 | not measured | unqualified | not measured |

Qualified frontier: none.
