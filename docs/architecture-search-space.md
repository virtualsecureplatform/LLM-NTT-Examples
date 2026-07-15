# Architecture Search Space

This repository can be used as an example problem for agentic architecture
search. The fixed part of each task is the top-level I/O contract and reference
behavior. The variable part is the microarchitecture used to satisfy that
contract.

## Fixed Task Contract

For each task, a generated candidate must preserve:

- top module name
- top-level port names and widths
- reset polarity
- input and output stream ordering
- packed-lane layout
- field modulus
- transform direction and twist convention
- exact correctness behavior checked by the task manifest

The machine-readable version of this contract is in `tasks/*.json`. The human
description is in `docs/ntt-module-specs.md`.

## Search Axes

### Architecture Family

Agents should consider at least these families:

- `iterative`: reuse a smaller number of butterfly units across stages.
- `streaming_dataflow`: pipeline multiple or all stages with streaming buffers.
- `hybrid`: unroll a subset of stages and reuse that pipeline across rounds.
- `behavioral_reference`: simulation-oriented Verilog that prioritizes passing
  correctness tests, useful as a sanity baseline but not a hardware-quality
  endpoint.

For synthesis-oriented results, `behavioral_reference` should be reported
separately from hardware designs.

### Parallelism

Useful knobs:

- lanes per cycle
- butterfly units per stage
- number of parallel butterfly groups
- radix per stage
- number of cycles per full polynomial
- number of independent limbs, for AutoNTT-style RNS exploration

The extracted examples cover:

- YATA RAINTT: 512 coefficients, 64 lanes, 8 cycles, radix 8.
- HOGE streaming INTT: 1024 coefficients, 32 lanes, 32 cycles, radix 32.
- HOGE NTTid: 1024 coefficients packed as a full vector.

### Radix Schedule

Candidate designs may use a different internal radix schedule than the extracted
RTL if the observable stream behavior is unchanged.

Typical choices:

- radix-2: simplest butterflies and control, more stages.
- radix-4 or radix-8: moderate control complexity, fewer stages.
- radix-16 or radix-32: high throughput, wider butterflies and harder routing.
- mixed radix: useful when matching stream width or buffer banks.

### Modular Multiplication

Modulo multiplication usually dominates DSP and latency cost. Search should
include:

- naive product and division, for simulation only or as a poor baseline
- Barrett reduction
- Montgomery reduction
- word-level Montgomery reduction
- prime-specific reduction

The two included primes are intentionally interesting:

- YATA: `40960001 = 5^4 * 2^16 + 1`, compact 27-bit compressed RAINTT prime.
- HOGE: `0xffffffff00000001 = 2^64 - 2^32 + 1`, a 64-bit pseudo-Mersenne prime.

Prime-specific reduction is a good search dimension because it may reduce DSPs,
pipeline depth, and LUT cost compared with generic reduction.

### Twiddle Strategy

Agents may choose:

- full ROM tables
- stage-local ROM tables
- generated powers from a primitive root
- compressed twiddle tables with recurrence
- pre-twisted constants
- separate NTT and INTT tables or shared tables with inversion logic

The task output must still match the TFHEpp reference tables.

### Memory And Permutation

NTT accelerators are often limited by buffering and routing, not just arithmetic.
Search should include:

- single buffer vs double buffer
- transpose buffer implementation
- bank count and bank mapping
- read/write port count
- shift-register stream buffers
- explicit SRAM/BRAM/URAM mapping for synthesis flows
- bit-reversal or hardware-friendly stage ordering

The task manifests specify externally visible ordering. Internal ordering is
free as long as the output order matches.

### Control

Streaming tasks need valid/ready timing decisions:

- fixed-latency pipeline
- elastic pipeline
- input stalls allowed or disallowed
- output valid burst length
- reset-to-ready latency

The current tests assume no input backpressure for `YataRainttTop` and
`INTTWrap`. `NTTWrap` exposes `io_ready`, but the repository currently treats it
as an interface/lint task until a reference test is added.

### Arithmetic Pipeline

The YATA Chisel generator exposes `baseline`, `f300`, and `deep` profiles. The
profiles tune multiplier delay and signed-reduction pipeline depth while all
butterfly, buffer, twiddle-index, output, and valid delays are derived from the
same configuration. This keeps the external 64-lane, eight-cycle stream
contract fixed while allowing latency/fmax exploration. Use
`--candidate-source chisel_pipeline --arch-type D --modmul-type C`; the fixed
architecture and reduction flags prevent a generated profile from being
mislabelled as an unsupported datapath.

For a target at or above 300 MHz, `AUTO` explores `f300`, `deep`, then
`baseline`. The `f300` point splits the original two-multiply SREDC critical
path and increases measured INTT/NTT wait latency from 34/35 to 40/41 cycles;
the input and output bursts remain eight cycles.

Keep `hoge_streaming_ntt_1024_p64` in `tier0_interface` comparisons only. It is
useful for checking module shape and packed-port compatibility, but it should
not appear in arithmetic, latency, throughput, or resource Pareto rankings. Use
`hoge_externalproduct_ntt_1024_p64` for the HOGE forward NTT arithmetic
boundary.

## Task Difficulty Levels

Suggested benchmark tiers:

- `tier0_interface`: module elaborates with the required ports.
- `tier1_correctness`: passes Verilator tests against TFHEpp.
- `tier2_latency`: passes correctness and improves valid latency.
- `tier3_resource`: passes correctness and improves synthesis resource use.
- `tier4_pareto`: produces a Pareto frontier across latency, throughput, and
  resources.

The current evaluator directly supports `tier0_interface` and
`tier1_correctness`. With `--with-yosys`, it also records a flattened structural
cell-count estimate that can seed `tier3_resource` screening. Vendor synthesis
reports are still needed for FPGA-specific LUT, FF, DSP, BRAM, URAM, and fmax
ranking.

Planned task skeletons under `tasks/planned/` document future benchmark
boundaries. They are not current evaluator targets.

## Recommended Agent Loop

1. Read the task manifest.
2. Generate or modify candidate Verilog in a candidate directory.
3. Run `scripts/evaluate_candidate.sh --task <task> --verilog-dir <dir>`.
4. Parse `results.json`.
5. If correctness fails, inspect the generated logs and fix the contract issue.
6. If correctness passes, optionally rerun with `--with-yosys` and optimize
   latency, throughput, or resources.
7. Keep every candidate result for Pareto analysis.

The agent should treat correctness as a hard gate. A faster design that fails
the reference test has score zero.
