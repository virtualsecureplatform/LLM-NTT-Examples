# Running architecture search

The implementation provides a reproducible search loop around NGen, optional
SGen square permutations, independent generic NTT checking, and staged Vivado
measurement. It does **not yet establish an advantage over AutoNTT, Proteus,
or OpenNTT**. Such a claim requires matched, independently verified baselines
and routed timing closure.

## Build and run

Build `NGen` with `sbt test assembly`. For SGen composition, build `SGen` with
`sbt 'testOnly transforms.perm.SwitchTransposeTest' assembly`.

Use Python 3.9+, Icarus Verilog, and Java. Existing preset tests additionally
require Verilator, modern CMake, and Clang with `_BitInt` support. GCC is rejected:
substituting 32-bit arithmetic for TFHEpp's 27-bit arithmetic changes the oracle.
Vivado 2023.2 is needed only for synthesis/route. On this workspace, the locally
installed verification tools can be enabled with `source /tmp/check-native-tools.sh`;
those temporary installations are not portable dependencies.

From `LLM-NTT-Examples`:

```bash
python3 scripts/search_architectures.py --campaign campaigns/smoke.json \
  --output-dir build/my-search --mode plan
python3 scripts/search_architectures.py --campaign campaigns/smoke.json \
  --output-dir build/my-search --mode run
python3 scripts/search_architectures.py --campaign campaigns/smoke.json \
  --output-dir build/my-search --mode resume
```

`plan` validates/enumerates without running tools or writing artifacts. `run`
requires an empty output directory. `resume` requires identical source hashes,
generator binaries, tools, workload, policy, and constraints. Each run snapshots
the generator binaries. Records include commands, logs, hashes, elapsed time,
failures, declared metadata, and measured evidence. Exact duplicate RTL is skipped.
An interrupted attempt consumes its reserved budget; resume does not grant free
retries. `report` regenerates JSON/Markdown summaries without rerunning hardware.

Campaign budgets default to 12 hours, 64 functional checks, 12 synthesis jobs,
and 4 route jobs, with a per-user lock allowing one Vivado job at a time across campaigns. Queue
time consumes the budget. Functional checks precede
implementation. Hardware shortlisting starts with smaller PE/stage-group counts;
routing prioritizes synthesis timing closure. This is a simple heuristic, not a
proven optimal acquisition policy. Budgets apply per campaign, not to a directory
of campaigns collectively.

## Search axes and protocols

Generic candidates vary PE count, radix 2/4/8, Barrett/Montgomery/Shoup reduction,
and contiguous stage groups. Groups greater than one currently require radix 2.
`NGen capabilities` reports the public capability contract; `NGen plan <generator
arguments>` performs actual lowering into a temporary directory and emits metadata.
The plan command is not a constant-time analytical estimator.

NGen's `-stage-groups U` creates U independent buffered PE engines linked by
ready/valid. Each engine owns a contiguous set of stages and two coefficient
buffers. This is a partially unrolled **buffered pipeline**, not an SDF/MDC or
AutoNTT feedback architecture. More groups can improve initiation interval at the
cost of buffers, arithmetic, and latency. Metadata describes the generated core;
the generic benchmark additionally includes one elastic register at each boundary.
Simulation and resource measurements include both registers. External lane count
is fixed by the workload and does not silently change with PE count.

The generic oracle uses Python arbitrary-precision integers, exact roots, natural
input/output order, forward/inverse scaling, and negacyclic twist/untwist. Small
transforms cross-check FFT evaluation against the direct definition and a schoolbook
negacyclic convolution. RTL checks cover zero, q−1, impulse, ramp, alternating and
seeded random inputs, consecutive frames, source/sink stalls, output stability,
extra output detection, and reset with work in flight. Latency is first-frame
latency; maximum loaded latency is separate. Frame interval is measured under
saturated traffic. Preset evaluators retain their own arithmetic contract and report
transaction cycles; they do not supply a fabricated sustained throughput.

```bash
python3 scripts/search_architectures.py --campaign campaigns/partitioned-smoke.json \
  --output-dir build/partitioned --mode run
python3 scripts/check_permutation_generators.py --output-dir build/permutations
python3 scripts/search_architectures.py --campaign campaigns/yata8x8-sgen.json \
  --output-dir build/yata-sgen --mode run
python3 scripts/make_fhe_campaigns.py --output-dir build/fhe-workloads
```

The FHE matrix contains exact primes/roots for N=16K/64K/128K, widths 32/54/64,
and both directions. Generation of campaign files is not a claim that all resulting
hardware fits or has been tested. SGen composition currently replaces supported
unprefixed square switch networks in NGen presets, retaining the packed valid/data
boundary. Both source revisions and binaries are recorded. SGen's standalone NTT
arithmetic is not assumed. Rectangular and linear-permutation composition remain
outside the implemented search space.

## LLM and empirical costs

```bash
python3 scripts/search_architectures.py --campaign campaigns/smoke.json \
  --output-dir build/llm-search --policy llm --mode run
```

The default endpoint is `http://kunashiri.sato.lab:8080/v1`; `/models` resolves the
model unless the campaign's `llm.model` supplies it. Optional settings are `endpoint`,
`timeout_seconds`, and `api_key_env` (default `NTT_LLM_API_KEY`). The LLM can only
rank prevalidated configuration IDs. Unknown IDs and duplicates are rejected.
Requests/responses/selections are saved; failures use recorded seeded-random
fallback. No generated code or claimed metrics are executed or accepted.
`--policy random --seed N` provides a control under the same budgets.

```bash
python3 scripts/calibrate_architecture_cost.py --campaign campaigns/smoke.json \
  --reports build/my-search/report.json --output build/cost.json
python3 scripts/search_architectures.py --campaign campaigns/smoke.json \
  --output-dir build/cost-search --policy cost --cost-model build/cost.json --mode run
```

The initial cost model uses three nearest configurations, records leave-one-out
absolute errors, and only uses matching workloads/targets with successful
implementation evidence. Fewer than three distinct samples do not produce a
validation error estimate. Cost-guided ordering uses predicted LUT count with
one-quarter exploration. It does not prune designs, create measured evidence,
or guarantee prediction accuracy. Cross-workload fitting, richer acquisition
functions, and a measured LLM-versus-random search advantage remain future work.

## Hardware evidence and references

Add `"stages": ["simulation", "synthesis", "route"]` to enable implementation.
The default target is U280 `xcu280-fsvh2892-2L-e`, Vivado 2023.2, 4 ns. Routing
uses out-of-context implementation at the registered generic boundary. The legacy
default is zero input/output delay. Targets can explicitly specify `clock_source`
(an existing BUFG site for `HD.CLK_SRC`) and `io_delays_ns` with `input_min`,
`input_max`, `output_min`, and `output_max`. These fields belong to the comparison
contract and must match across candidates. `campaigns/u280-registered-smoke.json`
exercises a declared synchronous interface (input arrival 0.2–1.0 ns, output
requirement 0–1.0 ns) with `BUFGCE_X0Y0`; it is a diagnostic 6 ns case. This is an explicit core timing convention, not a board timing
model. Both setup and hold must pass; a routed checkpoint alone is insufficient.
Whole-device resource totals are retained when reports also contain per-SLR rows.
Incomplete routing, failed tools, missing measurements, and failed correctness
cannot enter the corresponding Pareto frontier. `resource_limits` supplies upper
bounds such as `lut`, `dsp`, `bram`, and `uram`. No board execution is included.

```bash
python3 scripts/prepare_openntt_baseline.py --campaign campaigns/fhe16k54.json \
  --output-dir build/openntt-reference --pe 2 --memory-opt 0
```

The OpenNTT adapter copies generator inputs into an isolated tree and supplies
exact q/root/inverse-root values. It records minimal portability edits: naming
inactive custom-module instances, typing the ROM filename as a string, and sizing
the fixed modulus literal. Before/after hashes identify every edit; arithmetic
and the selected FPGA datapath are unchanged.

```bash
python3 scripts/check_openntt_baseline.py --baseline-dir build/openntt-reference
python3 scripts/check_openntt_baseline.py --baseline-dir build/openntt-reference --stream
```

The first command checks the physical host-memory interface against the independent
oracle, including explicit bit-reversal and bank ordering. The second synthesizable
adapter exposes the same registered ready/valid stream as generic NGen candidates.
It includes two frame buffers, scalar host load/readout at one coefficient per
cycle, ordering conversion, and elastic boundary registers in all measurements.
Backpressure, reset during capture/computation, repeated frames, and output stability
use the common streaming checker. Artifact and verification hashes guard against
using changed sources or vectors as cached evidence.

```bash
python3 scripts/search_architectures.py --campaign campaigns/openntt-overlap256.json \
  --output-dir build/ngen-overlap --mode run
python3 scripts/compare_openntt_ngen.py --campaign campaigns/openntt-overlap256.json \
  --ngen-report build/ngen-overlap/report.json \
  --openntt-dirs build/openntt-256-32 build/openntt-memopt-256-32 \
  --output-dir build/comparison
```

Prepare the referenced baseline directories first with the same campaign and
`--memory-opt 0`/`1`, then run `--stream` verification. The comparison command
requires equal workloads, targets, and normalized boundaries. Generation-only
results cannot enter the frontier. OpenNTT's `io_band` remains internal PE
bandwidth, not the external stream width. See [current comparison evidence](openntt-comparison.md).

The local Proteus tree informed the architecture choices, but it is not yet an
executable search adapter. Its hard-coded field/operation variants must be mapped
to exact workloads before comparison. Native SDF/MDC, twiddle recurrence search,
RNS/batch resource accounting, and matched routed paper comparisons remain open
parts of the larger roadmap.

## Verification from this implementation session

- NGen: 145 Scala tests passed; square switch regressions passed.
- SGen: three focused Scala tests passed; both generators passed all five square
  stream sizes. The broad SGen suite was stopped after expanding into unrelated
  FFT generation; it is not reported as passing.
- Search/oracle/reporting: 16 Python tests passed.
- All eight stage-group/PE smoke candidates passed; 12 inverse candidates with
  64-bit primes passed, including registered boundaries and backpressure.
- A 16K/54-bit forward candidate passed the independent RTL oracle.
- Native and SGen-composed YATA candidates passed the full existing oracle.
- The LLM endpoint successfully ranked four legal smoke candidates, all correct.
- Registered N=16 synthesis passed at 6 ns. Routing completed but failed hold
  timing (−0.079 ns), correctly leaving the route frontier empty. There is no
  routed performance-win claim.

Run artifacts are under `build/search-*`, `build/permutation-comparison`, and
`build/openntt-fhe16k54-2`. They are ignored generated files, not committed results.
