# Wide Montgomery product pipeline

NGen `1ed41d6` uses nine pipeline stages for Montgomery butterflies above 32 bits,
retaining seven stages for smaller fields. The first product is split into four
half-word products, followed by two registered addition stages. Bypass constants
are converted to an ordinary multiplier value of one before those stages. The
existing correction/reduction path remains, with valid, kind, operand, bypass
and transaction-tag delays extended consistently. Generator cycle estimates and
emitted butterfly latency metadata use the actual field width.

The motivation is the N=16384/q54 synthesis path through a multi-DSP product to
the correction multiplier: WNS -0.292 ns under the 4 ns contract. Extra pipeline
registers can trade area/latency for timing; this change does not yet establish
closure or a resource improvement.

Validation uses a fresh `sbt assembly test` build. All 151 Scala tests pass,
including 240-cycle direct arithmetic/tag/valid sequences for each of 33-, 54-
and 64-bit fields, bypass cases, bubbles, and two mid-stream reset points.
The rebuilt executable passes full N=256 forward/inverse oracles for both 54-
and 64-bit fields in `build/wide-product-rebuilt256-q*-*`.

The rebuilt 16K/q54 forward campaign passes eight frames with first-output
latency 69803 and initiation interval 73896, versus 69773/73866 for the separately
rebuilt block-ROM-only revision. The 30-cycle difference matches two additional
cycles across 15 drained stages. Its hardware candidate is `afb34bb930a4`
(prefix), in `build/ngen-fhe16k54-wide-product-rebuilt`; synthesis is queued.
`campaigns/fhe16k54-wide-product.json` preserves the exact matched fabric target.
The full 18-case FHE run is active in `build/fhe-wide-product-rebuilt-matrix`.

Earlier directories named `wide-product256-q*-*` were generated with an older
assembled executable and do not validate this change. The corrected directories
include `rebuilt`. This attribution error and the corresponding block-ROM
correction are retained in the completion audit; no older measurement is
promoted to evidence for the new pipeline.

The rebuilt full FHE matrix completed: all 18 cases pass (N=16384/65536/131072,
32/54/64-bit fields, forward/inverse). Matched 16K/q54 synthesis also completed:

| Implementation | LUT | FF | DSP | BRAM | Setup WNS (ns) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original distributed control, seven-stage arithmetic | 114739 | 2807 | 52 | 48 | -0.292 |
| Block control, nine-stage wide arithmetic | 8201 | 3301 | 66 | 376 | +0.955 |

These are synthesis results under the identical 4 ns fabric contract. The
combined change trades BRAM/DSP/FF and +30 cycles for lower LUT use and passing
estimated setup timing. Block-only synthesis remains pending, so this table
does not assign the individual resource benefits to one optimization.
`campaigns/fhe16k54-wide-product-route.json` now queues routed confirmation in
`build/ngen-fhe16k54-wide-product-route` after fresh simulation.

The original routed implementation completed with LUT 113238, FF 3909, DSP 52,
BRAM 48, setup WNS -0.739 ns and hold slack +0.010 ns. Full implementation
completed, but failed setup excludes it from the 250 MHz routed frontier. Its
critical path still crosses the wide DSP product to `product_1_reg`.

The block-only ablation is now complete: 8975 LUT, 2851 FF, 52 DSP, 376 BRAM,
WNS -0.292 ns. With identical block control, the wide-product pipeline changes
those values to 8201 LUT, 3301 FF, 66 DSP, 376 BRAM and WNS +0.955 ns. Thus the
ROM change accounts for most LUT savings; the arithmetic change adds 14 DSPs,
450 FFs and 30 frame cycles while improving estimated setup by 1.247 ns.
The distinct source revisions and RTL artifacts remain in their respective
candidate records; no combined-change result is substituted for the ablation.

Routed confirmation completed: 7920 LUT, 3417 FF, 66 DSP, 376 BRAM, setup WNS
-0.459 ns and hold +0.010 ns. Full routing completes but setup still fails at
4 ns, so the design remains ineligible for the 250 MHz routed frontier. The
worst path moved from the original wide product to control-ROM output feeding
a coefficient-memory enable (`control_0_reg_0_130` to
`buffer_0_bank_0_reg_bram_3/ENBWREN`). The synthesis improvement is real at its
reported stage; it must not be represented as routed timing closure.
