# Conservative resource-capacity pruning

The search now applies a necessary state-capacity test before generation for
the closed NGen streamed ready/valid core on U280. It uses complete declared
`resource_limits` for LUT, FF, DSP, BRAM tiles, and URAM. An omitted cap is
unbounded; in particular, omitted URAM never means zero. Unsupported generators,
interfaces, or parts leave this bound unavailable.

This architecture accepts an entire frame before producing an output. After
N−1 inputs, an invertible NTT must distinguish q^(N−1) possible input prefixes,
even if the last coefficient is identical in every continuation. It therefore
needs at least (N−1) floor(log2(q)) bits of state. This intentionally omits the
last coefficient, additional frame buffers, stage replication, and control and
twiddle storage. It is a necessary information-capacity bound, not an estimate
of the generated array size or achieved utilization.

The upper capacity model assumes every LUT can hold 64 writable bits and gives
RAM and DSP primitives generous allowances for internal pipeline state:

| Capped resource | Upper state allowance, bits |
| --- | ---: |
| LUT | 64 |
| FF | 1 |
| DSP | 4096 |
| BRAM tile | 65536 |
| URAM | 524288 |

These padded RAM/DSP allowances are deliberately larger than usable memory.
AMD documents the underlying 64-bit distributed RAM, 36-Kbit BRAM, and
288-Kbit UltraRAM capacities in [Internal Memory](https://docs.amd.com/r/en-US/conversion-methodology/Internal-Memory).
The [DSP48E2 register attributes](https://docs.amd.com/r/en-US/ug974-vivado-ultrascale-libraries/DSP48E2)
and [UltraRAM register attributes](https://docs.amd.com/r/en-US/ug573-ultrascale-memory-resources/UltraRAM-Attributes)
describe their bounded internal pipeline state. The generous envelopes prevent
that state from being incorrectly ignored. This model is limited to the emitted
closed OOC logic/RAM/DSP design, with no external-memory or hard-IP storage.

Pruning occurs only when the lower state requirement exceeds the summed upper
capacity; equality is retained. Predictions from the fitted cost model never
enter this decision. Passing the bound proves neither port feasibility, resource
fit, nor timing closure.

`build/storage-pruning-validation` checks N=65536/q54 with caps LUT=10000,
FF=6000, DSP=50, BRAM=8, URAM=0. Its prefix requires at least 3473355 state
bits, while the padded resource envelope supplies at most 1375088 bits.
The candidate is recorded as `pruned`, with no evidence and zero functional,
synthesis, or route evaluations consumed. Both the state and throughput bounds
are retained in its record. Four focused tests cover the impossible state,
missing caps, equality, DSP state, unknown targets, and invalid values; the
complete 107-test Python suite passes.
