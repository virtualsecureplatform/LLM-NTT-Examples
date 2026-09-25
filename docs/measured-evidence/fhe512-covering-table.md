# N=512 pre-route screening

Grid: `covering`; 18 architectures; 19/22 planned points completed Yosys screening; 19 unique RTL hashes among passed points.

Covered axes: backend={stage-parallel, streamed}, lanes={2, 4}, pe={1, 2, n/a}, radix={2, 8}, stage_groups={1, 2}, reduction={barrett, montgomery, shoup}, profile={baseline, f300}, transpose={indexed}.

The cell counts are coarse Yosys operators after memory lowering, not U280 LUTs. Throughput is products per 1,000 cycles; no achieved clock or routed throughput is inferred.

| Frontier point | Error bound | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ngen-streamed-l2-pe1-r2-s1-shoup-baseline-q0` | 0 | 1,849,578 | 8,067 | 3,390 | 0.295 |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-q0` | 0 | 1,875,903 | 5,252 | 1,983 | 0.504 |
| `ngen-streamed-l2-pe2-r8-s1-barrett-baseline-q0` | 0 | 2,667,480 | 5,004 | 2,113 | 0.473 |
| `ngen-streamed-l4-pe2-r2-s1-barrett-baseline-q0` | 0 | 4,650,453 | 4,484 | 1,727 | 0.579 |
| `ngen-streamed-l4-pe2-r8-s1-barrett-baseline-q0` | 0 | 5,535,234 | 4,236 | 2,113 | 0.473 |

## All evaluated configurations

Each row is one complete N=512 polynomial product. `q4` rounds output to multiples of 16; all other points are exact (`q0`). `—` means no Yosys cell result. 22/22 points passed RTL simulation. A point is resource-qualified only when its status is `screened`.

| Configuration | Error bound | Observed error | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-q0` | 0 | 0 | 1,849,587 | 8,067 | 3,390 | 0.295 | screened |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-q4` | 8 | 8 | 1,849,590 | 8,067 | 3,390 | 0.295 | screened |
| `ngen-streamed-l2-pe1-r2-s1-barrett-f300-q0` | 0 | 0 | 1,849,587 | 8,067 | 3,390 | 0.295 | screened |
| `ngen-streamed-l2-pe1-r2-s1-montgomery-baseline-q0` | 0 | 0 | 1,849,884 | 8,147 | 3,430 | 0.292 | screened |
| `ngen-streamed-l2-pe1-r2-s1-montgomery-baseline-q4` | 8 | 8 | 1,849,887 | 8,147 | 3,430 | 0.292 | screened |
| `ngen-streamed-l2-pe1-r2-s1-shoup-baseline-q0` | 0 | 0 | 1,849,578 | 8,067 | 3,390 | 0.295 | screened |
| `ngen-streamed-l2-pe1-r2-s2-barrett-baseline-q0` | 0 | 0 | 2,363,622 | 9,097 | 2,080 | 0.481 | screened |
| `ngen-streamed-l2-pe1-r8-s1-barrett-baseline-q0` | 0 | 0 | 1,998,420 | 7,686 | 4,219 | 0.237 | screened |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-q0` | 0 | 0 | 1,875,903 | 5,252 | 1,983 | 0.504 | screened |
| `ngen-streamed-l2-pe2-r8-s1-barrett-baseline-q0` | 0 | 0 | 2,667,480 | 5,004 | 2,113 | 0.473 | screened |
| `ngen-streamed-l4-pe1-r2-s1-barrett-baseline-q0` | 0 | 0 | 4,642,020 | 7,299 | 3,134 | 0.319 | screened |
| `ngen-streamed-l4-pe1-r2-s1-barrett-f300-q0` | 0 | 0 | 4,642,020 | 7,299 | 3,134 | 0.319 | screened |
| `ngen-streamed-l4-pe1-r2-s1-montgomery-baseline-q0` | 0 | 0 | 4,642,317 | 7,379 | 3,174 | 0.315 | screened |
| `ngen-streamed-l4-pe1-r2-s1-shoup-baseline-q0` | 0 | 0 | 4,642,011 | 7,299 | 3,134 | 0.319 | screened |
| `ngen-streamed-l4-pe1-r2-s2-barrett-baseline-q0` | 0 | 0 | 5,191,758 | 7,817 | 1,824 | 0.548 | screened |
| `ngen-streamed-l4-pe1-r8-s1-barrett-baseline-q0` | 0 | 0 | 4,796,388 | 6,918 | 4,219 | 0.237 | screened |
| `ngen-streamed-l4-pe2-r2-s1-barrett-baseline-q0` | 0 | 0 | 4,650,453 | 4,484 | 1,727 | 0.579 | screened |
| `ngen-streamed-l4-pe2-r8-s1-barrett-baseline-q0` | 0 | 0 | 5,535,234 | 4,236 | 2,113 | 0.473 | screened |
| `ngen-streamed-l4-pe2-r8-s1-barrett-baseline-q4` | 8 | 8 | 5,535,237 | 4,236 | 2,113 | 0.473 | screened |
| `ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline-q0` | 0 | 0 | — | 1,818 | 521 | 1.919 | Yosys timeout |
| `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q0` | 0 | 0 | — | 1,306 | 256 | 3.906 | Yosys timeout |
| `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q4` | 8 | 8 | — | 1,306 | 256 | 3.906 | Yosys budget stop |

Points without complete screening: 3.
- `ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline-q0`: Yosys timeout
- `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q0`: Yosys timeout
- `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q4`: Yosys budget stop
