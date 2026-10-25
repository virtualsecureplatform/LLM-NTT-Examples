# LLM-guided polynomial multiplication DSE

Mode: **live**. Exact N=512 full32 × ternary products modulo 2^32; U280, registered harness v2, Default implementation, 250 MHz. Each policy receives the same passing seed as disclosed prior evidence.

| Policy | Status | New candidates | Maps | Routes | Feasible incl. seed | Best modeled products/s | Hypervolume | New physical maps/routes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| llm | complete | 4 | 4 | 2 | 2 | 141482.7 | 1.8838 | 3/2 |
| random | complete | 4 | 4 | 2 | 2 | 141482.7 | 1.8838 | 2/1 |
| analytical | complete | 4 | 4 | 2 | 1 | 72886.3 | 0.9764 | 2/2 |

| Policy | Achieved design | LUT | FF | DSP | BRAM36 | Modeled products/s | Setup ns | Hold ns |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| llm | pipelined montgomery L2 PE1 | 24612 | 12767 | 60 | 51 | 72886.3 | 0.063 | 0.011 |
| llm | pipelined montgomery L4 PE2 | 37359 | 16001 | 96 | 66 | 141482.7 | 0.012 | 0.01 |
| random | pipelined montgomery L2 PE1 | 24612 | 12767 | 60 | 51 | 72886.3 | 0.063 | 0.011 |
| random | pipelined montgomery L4 PE2 | 37359 | 16001 | 96 | 66 | 141482.7 | 0.012 | 0.01 |
| analytical | pipelined montgomery L2 PE1 | 24612 | 12767 | 60 | 51 | 72886.3 | 0.063 | 0.011 |

Hypervolume minimizes LUT and maximizes modeled throughput; fixed reference is the target LUT limit and zero throughput, normalized by LUT limit × common-seed throughput. Cache hits consume logical budgets. Physical execution counts depend on shared-cache reuse and policy order.

This is an exploratory single-seed demonstration, not evidence of a statistically established search advantage. Replay is a closed five-design integration fixture; no complete 24-design reference frontier was measured. Products/s are modeled from qualified cycles and the bandwidth assumption, not board measurements.

[Comparison CSV](llm-dse-live-512.csv) · [Point CSV](llm-dse-live-512-points.csv) · [Provenance and metrics](llm-dse-live-512.json)

![Area and search progress](llm-dse-live-512.svg)

Across policies: 9 distinct candidates acquired (including the common seed), 6 distinct candidates routed. New physical work: 5 qualifications, 7 mappings, and 5 routings.

[PNG](llm-dse-live-512.png) · [SVG](llm-dse-live-512.svg)
