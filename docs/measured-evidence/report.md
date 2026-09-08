# NTT generator evidence snapshot

Snapshot of named comparisons, not certification that the full project plan is complete. Legacy hardware evidence remains explicitly unverified by newer manifests.

## N=256/q32 three-generator comparison

Same two-buffer fabric contract. All three designs pass timing; resource and throughput tradeoffs remain.

Workload: `{"direction": "forward", "kind": "generic", "lanes": 4, "n": 256, "negacyclic": true, "psi": "1421553366", "q": "2147484161", "root": "2141337746"}`

Target: `{"clock_period_ns": 4.0, "clock_source": "BUFGCE_X0Y0", "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "input_full_reg/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/comparison-threeway256-compact-routed`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 3648c6c030fc | {"architecture": "mdc", "boundary": "registered-ready-valid", "generator": "Proteus", "mdc_inverse_rom_repair": true, "montgomery_loops": 4, "montgomery_word_bits": 9, "op": 1, "reduction": "montgomery"} | True | True | 17366 | 21750 | 64 | 0 | 0.407 | 0.01 | legacy-unverified |
| 38a214c07446 | {"backend": "streamed", "boundary": "registered-ready-valid", "generator": "ngen", "lanes": 4, "pe": 2, "profile": "baseline", "radix": 2, "reduction": "montgomery", "stage_groups": 1, "transpose": "indexed"} | True | True | 4904 | 1950 | 18 | 4 | 0.24 | 0.006 | legacy-unverified |
| cc1401ed0118 | {"boundary": "registered-ready-valid", "generator": "OpenNTT", "memory_opt": 0, "ntt_type": "mfntt_dit_nr", "pe": 2} | True | True | 10193 | 11142 | 32 | 3 | 0.791 | 0.01 | legacy-unverified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 3648c6c030fc | 740 | 802 | 2960.0 | 311720.6982543641 |
| 38a214c07446 | 791 | 852 | 3164.0 | 293427.23004694836 |
| cc1401ed0118 | 1132 | 1194 | 4528.0 | 209380.23450586264 |

Qualified frontier: 3648c6c030fc, 38a214c07446, cc1401ed0118.

## N=16384/q54 NGen and OpenNTT

Both designs pass routed timing. Registered-issue NGen trades more LUT/BRAM for lower latency and fewer FF/DSP than OpenNTT. Earlier failed NGen revisions remain in separate reports.

Workload: `{"direction": "forward", "kind": "generic", "lanes": 4, "n": 16384, "negacyclic": true, "psi": "8877445661101042", "q": "9007199255560193", "root": "2574240303494213"}`

Target: `{"clock_period_ns": 4.0, "clock_source": "BUFGCE_X0Y0", "io_delays_ns": {"input_max": 1.0, "input_min": 0.5, "output_max": 1.0, "output_min": 0.0}, "io_reference_pin": "input_full_reg/C", "output_hold_buffer_stages": 2, "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **route**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/comparison16k54-registered-issue-routed`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2f6aafadf88d | {"boundary": "registered-ready-valid", "generator": "OpenNTT", "memory_opt": 0, "ntt_type": "mfntt_dit_nr", "pe": 2} | True | True | 5961 | 7198 | 68 | 74 | 0.275 | 0.01 | verified |
| 903e55c29f84 | {"backend": "streamed", "boundary": "registered-ready-valid", "generator": "ngen", "lanes": 4, "pe": 2, "profile": "baseline", "radix": 2, "reduction": "montgomery", "stage_groups": 1, "transpose": "indexed"} | True | True | 8423 | 3667 | 66 | 376 | 0.124 | 0.011 | verified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 2f6aafadf88d | 94257 | 98351 | 377028.0 | 2541.916198106781 |
| 903e55c29f84 | 69818 | 73911 | 279272.0 | 3382.4464558726036 |

Qualified frontier: 2f6aafadf88d, 903e55c29f84.

## Kyber storage and arithmetic ablation

Compact banked Kyber requires serialized host transactions and complete buffer loading. Synthesis qualification is not routed closure.

Workload: `{"kind": "preset", "task": "kyber_ntt_256_p12_pe1"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clk", "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **synthesis**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/kyber-storage-comparison`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| b10e0f6d802b | {"backend": "microcoded", "generator": "ngen", "profile": "baseline", "transpose": "indexed"} | True | True | 17056 | 9585 | 3 | 3 | 1.718 | -0.075 | legacy-unverified |
| cc3d27591e5d | {"generator": "extracted-rtl", "task": "kyber_ntt_256_p12_pe1"} | True | True | 777 | 353 | 1 | 2.5 | 1.307 | -0.042 | legacy-unverified |
| dcbc894765e2 | {"backend": "compact", "generator": "ngen", "profile": "baseline", "transpose": "indexed"} | True | True | 948 | 401 | 2 | 3 | 0.365 | -0.075 | legacy-unverified |
| f6c581ff9b90 | {"backend": "microcoded", "generator": "ngen", "profile": "baseline", "transpose": "indexed"} | True | False | 23165 | 9456 | 6 | 3 | -6.72 | -0.075 | legacy-unverified |
| febba1d0ac99 | {"backend": "compact", "generator": "ngen", "host_schedule": "serialized-load-compute-read", "profile": "baseline", "storage": "banked-pointer-swap", "transpose": "indexed"} | True | True | 628 | 223 | 2 | 1 | 0.704 | -0.075 | legacy-unverified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| b10e0f6d802b | 1414 | not measured | 5656.0 | not measured |
| cc3d27591e5d | 1414 | not measured | 5656.0 | not measured |
| dcbc894765e2 | 1414 | not measured | 5656.0 | not measured |
| f6c581ff9b90 | 1407 | not measured | unqualified | not measured |
| febba1d0ac99 | 1414 | not measured | 5656.0 | not measured |

Qualified frontier: cc3d27591e5d, febba1d0ac99.

## NGen and SGen YATA permutation choices

Composed switch/stride designs pass arithmetic but fail setup under the stated target.

Workload: `{"kind": "preset", "task": "small_yata8x8_raintt_p27"}`

Target: `{"clock_period_ns": 4.0, "clock_port": "clock", "part": "xcu280-fsvh2892-2L-e", "tool_version": "2023.2"}`

Stage: **synthesis**. Source: `/home/work-bleaker/kmatsuoka/sources/LLMNTT-workspace/LLM-NTT-Examples/build/yata8x8-permutation-comparison`.

| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 5049111e3b76 | {"backend": "microcoded", "generator": "ngen-sgen-linear", "profile": "baseline", "transpose": "switch"} | True | False | 58769 | 11306 | 424 | 8 | -5.483 | -0.075 | legacy-unverified |
| 7f19e997defb | {"backend": "microcoded", "generator": "ngen", "profile": "baseline", "transpose": "switch"} | True | False | 58565 | 9823 | 424 | 0 | -5.483 | -0.042 | legacy-unverified |
| 818225ba7242 | {"backend": "microcoded", "generator": "ngen-sgen", "profile": "baseline", "transpose": "switch"} | True | False | 58565 | 9823 | 424 | 0 | -5.483 | -0.042 | legacy-unverified |

| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |
| --- | ---: | ---: | ---: | ---: |
| 5049111e3b76 | 96 | not measured | unqualified | not measured |
| 7f19e997defb | 86 | not measured | unqualified | not measured |
| 818225ba7242 | 86 | not measured | unqualified | not measured |

Qualified frontier: none.

## Pending comparisons

- HOGE forward hardware comparison: `build/hoge-forward-hardware-comparison`
- HOGE inverse hardware comparison: `build/hoge-inverse-hardware-comparison`
