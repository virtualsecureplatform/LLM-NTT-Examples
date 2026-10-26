# Polynomial multiplication DSE: results and presentation guide

Present three connected results: a broad NGen/SGen polynomial multiplication
sweep, a physically qualified FPGA shortlist, and a budget-matched adaptive
search experiment. The existing measurements demonstrate the search workflow
and useful hardware tradeoffs. The live LLM experiment ties random search;
it does not yet establish that LLM selection reduces evaluation effort.

## Recommended presentation sequence

| Order | Question | Main document/table | Figure to present |
| --- | --- | --- | --- |
| 1 | What architecture and arithmetic tradeoffs does the grid reveal? | [Polynomial study results](results/polynomial-results.md), N=512 tables | [N=512 resources versus product interval](results/torus512-resource-throughput.svg) |
| 2 | How does approximation change the tradeoff? | Same report, FFT error/throughput section | [FFT error bound versus product interval](results/torus512-error-throughput.svg) |
| 3 | Which designs actually meet routed 250 MHz timing? | [Routed frontier and five-design table](results/pareto250-512.md) | [Routed resources versus modeled throughput](results/pareto250-512.svg) |
| 4 | Can a bounded LLM search acquire useful feasible designs? | [Live policy comparison](results/llm-dse-live-512.md) | [Live area/throughput and search-progress panels](results/llm-dse-live-512.svg) |
| 5 | How can someone use the tool? | [Experiment CLI guide](dse-tool.md) | A locally generated `report.html`; use [published replay panels](results/llm-dse-replay-512.svg) when presenting the recorded fixture |

For a short presentation, use figures 1, 3, and 4, plus the policy comparison
table below. Add figure 2 when approximate arithmetic is part of the discussion.
SVG is preferred for slides and zooming; each linked result report also provides
PNG versions. These figures already exist in the repository; no new hardware
campaign was run to prepare this summary.

## 1. Grid search: architecture and arithmetic

The broad study measures complete negacyclic polynomial products modulo `2^32`.
At N=512 it covers full32 × full32, full32 × signed-byte, and full32 × ternary
operands. NGen supplies streamed and stage-parallel NTT products; SGen supplies
compact and full-throughput FFT products, including two/four-lane full-throughput
variants. Controls include architecture, parallelism, modular reduction, FFT
precision, digit-diagonal omissions, and output rounding where supported.

| N=512 workload | Qualified | Certificate rejected | Timed out | Unsupported combinations |
| --- | ---: | ---: | ---: | ---: |
| full32 × full32 | 67 | 9 | 3 | 102 |
| full32 × signed-byte | 70 | 9 | 0 | 102 |
| full32 × ternary | 70 | 9 | 0 | 102 |
| Total | 207 | 27 | 3 | 306 |

Counts are from the [published grid report](results/polynomial-results.md).
Unsupported combinations are recorded backend exclusions, not completed
hardware evaluations. All three timeouts concern full32 × full32 compact FFT
measurements; they are incomplete measurements, not arithmetic failures.

![N=512 generic resources versus product interval](results/torus512-resource-throughput.svg)

Explain the figure as a resource/cycle tradeoff: lower interval means more
products per cycle; lower generic cell count means a smaller coarse logic
estimate. Both axes are logarithmic. Rings mark the seven-objective frontier
(error bound, cells, retained memory bits, register bits, multiplier operators,
latency, and interval), so they need not form a two-dimensional envelope.

For example, in the full32 × full32 workload, the exact streamed Shoup L2/PE1
NTT has 18,963 generic cells and a 3,390-cycle interval. The exact stage-parallel
Montgomery L4 NTT has 657,513 cells and a 256-cycle interval. The exact compact
FFT has 48,381 cells and a 505,844-cycle interval. These are useful contrasting
points, not a universal ranking: memory, multipliers, and other objectives also
matter. Generic cells and multiplier operators are not FPGA LUTs and DSPs.

![FFT error bound versus product interval](results/torus512-error-throughput.svg)

Use the second figure to explain how omitted digit diagonals reduce cycle cost
while increasing the analytical coefficient-error bound. Its symmetric-log
horizontal scale retains the exact zero-error points. Observed corpus maxima
and analytical bounds are different quantities; neither establishes an FHE
application's decryption reliability.

For the earlier controlled 46-design comparison, keep the
[common-pass NGen/SGen report](fhe512-common-frontier.md) and its
[per-configuration tables](measured-evidence/fhe512-common-frontier.md) as
backup. It screened 40 NGen and six SGen configurations and produced 13
seven-objective frontier points, including 11 exact-frontier points. That
snapshot has its own candidate set and synthesis evidence; do not merge its
counts or resource numbers with the later broad study.

Reproduction: [study setup and commands](polynomial-study.md).
Audit data: [N=512 CSV](results/torus512-points.csv) and
[grid provenance](results/provenance.json).

## 2. Physical feasibility: routed 250 MHz frontier

This narrower experiment fixes exact N=512 full32 × ternary multiplication,
U280 `xcu280-fsvh2892-2L-e`, Vivado 2023.2, Default implementation, and registered
on-chip harness v2. It measures total harness-plus-kernel resources. All five
published designs are routed, timing-feasible, and nondominated within this
measured pool under the full resource/latency/throughput objectives.

| Product profile | Lanes | PEs | LUTs | DSPs | BRAM36 | Interval cycles | Modeled products/s | Setup slack ns | Hold slack ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pipelined | 2 | 1 | 24,612 | 60 | 51 | 3,430 | 72,886.3 | +0.063 | +0.011 |
| registered | 2 | 1 | 19,427 | 60 | 60 | 3,430 | 72,886.3 | +0.219 | +0.010 |
| registered | 2 | 2 | 30,457 | 96 | 75 | 2,023 | 123,578.8 | +0.181 | +0.010 |
| registered | 4 | 1 | 29,487 | 60 | 63 | 3,174 | 78,765.0 | +0.113 | +0.012 |
| registered | 4 | 2 | 37,246 | 96 | 66 | 1,767 | 141,482.7 | +0.260 | +0.010 |

![Routed 250 MHz resource and modeled throughput tradeoffs](results/pareto250-512.svg)

The useful headline is **1.94× modeled throughput** relative to the original
pipelined seed, or **21% fewer LUTs at the same product interval** using the
registered L2/PE1 variant. The latter uses more BRAM; this is a tradeoff.
Rates derive from qualified kernel intervals at 250 MHz and the stated bandwidth
assumption. They are not measured board throughput. The on-chip harness does
not qualify external interfaces or board clock delivery. This is a five-design
measured frontier, not an exhaustive FPGA frontier.

Use the [initial timing-closure report](results/timing-closure-512.md) and its
[timing/resource figure](results/timing-closure-512.svg) as backup for signoff
questions. Reproduction and evidence requirements are in the
[device-aware search guide](device-polynomial-search.md).

## 3. LLM design space exploration: live comparison

The live prototype selects from 24 legal exact N=512 full32 × ternary streamed
NTT configurations: two product profiles × two lane counts × two PE counts ×
three modular reductions. Each policy gets the same passing pipelined Montgomery
L2/PE1 seed. It may acquire four additional candidates, four mappings, and two
routings. Failed attempts and cache hits consume the corresponding logical
budgets. The shared promotion scheduler is the same for all policies.

| Policy | Additional candidates | Maps | Routes | Feasible including seed | Best modeled products/s | Normalized hypervolume |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LLM | 4 | 4 | 2 | 2 | 141,482.7 | 1.8838 |
| Seeded random | 4 | 4 | 2 | 2 | 141,482.7 | 1.8838 |
| Analytical heuristic | 4 | 4 | 2 | 1 | 72,886.3 | 0.9764 |

![Live LLM, random, and analytical comparison](results/llm-dse-live-512.svg)

Present all three panels together: routed LUT versus modeled throughput,
hypervolume versus candidate attempts, and hypervolume versus routing attempts.
Hypervolume measures the LUT/throughput tradeoff using a fixed reference and
common-seed normalization. It is not the broad grid's seven-objective metric.
The seed is prior evidence and is excluded from the additional-trial budget.

Across policies, the experiment acquired nine distinct candidates including the
seed and routed six distinct candidates. Shared reuse required five new
qualifications, seven new mappings, and five new routings. Physical execution
counts depend on policy order and cache contents; logical budgets are the fair
comparison axis. The live L4/PE2 winning product is the **pipelined** variant,
with 37,359 LUTs and +0.012 ns setup slack. It differs from the registered
L4/PE2 point in the five-design frontier even though their modeled rates match.

The defensible conclusion is that the adaptive loop produces qualified designs
and inspectable budget/progress evidence. LLM and random tied in this single
seed experiment. There is no measured full 24-design routed reference frontier,
no multi-seed statistical comparison, and no demonstrated LLM advantage or
search-reduction factor. Those require additional experiments.

Methods and reproduction: [LLM search guide](llm-polynomial-search.md).
Audit data: [policy CSV](results/llm-dse-live-512.csv),
[achieved-point CSV](results/llm-dse-live-512-points.csv), and
[metrics/provenance JSON](results/llm-dse-live-512.json).

## 4. Tool demonstration and replay

Use the [unified experiment CLI](dse-tool.md) for a practical demonstration:

```bash
python3 -m architecture_search.dse init experiment.json
python3 -m architecture_search.dse preflight experiment.json
python3 -m architecture_search.dse run experiment.json
python3 -m architecture_search.dse status experiment.json
```

Open `build/dse/experiment/report.html` to show the automatically generated table,
tradeoff/progress graphs, and trial outcomes. The default compares random and
analytical policies offline using five bundled published measurements. Add
`--with-llm` to `init` and supply `LLM_DSE_API_KEY` to demonstrate LLM selection.
See the guide for live evaluation, configuration, resume, and report regeneration.

The [published replay report](results/llm-dse-replay-512.md) and
[replay graph](results/llm-dse-replay-512.svg) record a closed-fixture comparison:
LLM and analytical reached 78,765 modeled products/s; random reached 141,482.7.
Replay performs no new hardware evaluations. Portable replay validates the
bundled records and provenance but does not perform local RTL/checkpoint signoff.
Show replay as an integration/usability demonstration, separately from the live
search result and the broad grid. Fresh LLM calls can choose differently; the
published tables describe their recorded runs.
