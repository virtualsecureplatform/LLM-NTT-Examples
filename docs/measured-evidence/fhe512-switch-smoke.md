# N=512 pre-route screening

Grid: `smoke`; 2 architectures; 2/2 planned points completed Yosys screening; 2 unique RTL hashes among passed points.

Covered axes: backend={streamed}, lanes={2}, pe={1, 2}, radix={2}, stage_groups={1}, reduction={barrett}, profile={baseline}, transpose={switch}.

The cell counts are coarse Yosys operators after memory lowering, not U280 LUTs. Throughput is products per 1,000 cycles; no achieved clock or routed throughput is inferred.

| Frontier point | Error bound | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-switch-q0` | 0 | 3,941,550 | 8,585 | 3,906 | 0.256 |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-switch-q0` | 0 | 3,967,110 | 5,770 | 2,499 | 0.400 |

## All evaluated configurations

Each row is one complete N=512 polynomial product. `q4` rounds output to multiples of 16; all other points are exact (`q0`). `—` means no Yosys cell result. 2/2 points passed RTL simulation. A point is resource-qualified only when its status is `screened`.

| Configuration | Error bound | Observed error | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-switch-q0` | 0 | 0 | 3,941,550 | 8,585 | 3,906 | 0.256 | screened |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-switch-q0` | 0 | 0 | 3,967,110 | 5,770 | 2,499 | 0.400 | screened |

Points without complete screening: 0.
