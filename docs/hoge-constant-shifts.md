# HOGE radix constant specialization

The measured full-throughput forward baseline fails the 4 ns synthesis target
at WNS −8.332 ns and uses 2304 DSPs. Its radix-32 stages multiply by constants
that are powers of two modulo the Goldilocks prime. NGen branch
`hoge-constant-shifts`, revision `d277ab4`, replaces those radix factors with
constant modular shifts in both transform directions. Variable twiddle and
twist multiplications retain their existing implementation. Pipeline boundaries
and timing declarations are unchanged.

The shift implementation folds at 32-bit boundaries using
`2^64 = 2^32 - 1 (mod p)` and `2^96 = -1 (mod p)`, including carry/borrow and
canonical correction. The emitted SystemVerilog is checked against independent
BigInt modular exponentiation for all 192 exponents, seven boundary values and
32 random values per exponent (7488 checks). All 152 Scala tests pass in
`/tmp/ngen-hoge-shifts`; fresh assembly embeds the current source manifest.

`build/hoge-forward-shifts-validation` passes the unchanged complete forward
oracle with 104 transaction cycles. The separate overlap test in
`/tmp/llm-hoge-sgen/build/hoge-shifts-overlap` passes 240 random frames with
input gaps, five reset-abort positions and a saturated frame interval of 32
cycles. Its log is `/tmp/hoge-shifts-overlap.out`. The full inverse oracle also passes
in `build/hoge-inverse-shifts-validation`, candidate `3d54d358f3c7`.

The first forward synthesis attempt exhausted its queue budget without running
Vivado. The fresh retry in `build/hoge-forward-shifts-hardware-retry` completed.
The same-workload forward ablation is:

| Metric | Original | Constant shifts |
| --- | ---: | ---: |
| LUT | 214565 | 177390 |
| FF | 45852 | 47528 |
| DSP | 2304 | 1024 |
| BRAM / URAM | 0 / 0 | 0 / 0 |
| Setup WNS (ns) | -8.332 | -8.937 |
| Hold slack (ns) | -0.029 | -0.029 |
| Transaction cycles | 104 | 104 |

Shifts reduce DSP use by 55.6% and LUT use by 17.3%, while increasing FF use
by 3.7% and worsening setup slack by 0.605 ns. Both miss the 4 ns target.
Retain the specialization as a measured resource tradeoff; it does not supply
a qualified throughput advantage. The four-way consolidated comparison in
`build/hoge-forward-architecture-comparison` includes SGen composition (same
resources/timing as original NGen) and the extracted reference, which alone
passes synthesis setup. Main NGen remains frozen for the policy experiment.

Reproduce functional checks with the two `hoge-*-shifts-validation.json`
campaigns and an assembled checkout of the experimental NGen revision:

```sh
python3 scripts/search_architectures.py --campaign campaigns/hoge-forward-shifts-validation.json --ngen-root /path/to/ngen-hoge-shifts --output-dir build/fresh-hoge-shifts-forward --mode run
python3 scripts/search_architectures.py --campaign campaigns/hoge-inverse-shifts-validation.json --ngen-root /path/to/ngen-hoge-shifts --output-dir build/fresh-hoge-shifts-inverse --mode run
```

The inverse full-throughput implementation has now completed synthesis in
`build/hoge-inverse-full-throughput-hardware`, using the prepared NGen
integration `f4032e9`. The unchanged oracle passes at 73 transaction cycles.
Synthesis reports 136166 LUT, 34058 FF, 512 DSP, zero BRAM/URAM, setup
WNS −9.844 ns and hold −0.029 ns. It fails the 4 ns setup requirement.
This is an inverse architecture comparison, not a same-architecture inverse
shift ablation: no pre-shift inverse hardware measurement is available.
The completed matched forward ablation above establishes the measured
resource and timing effects for that direction.
