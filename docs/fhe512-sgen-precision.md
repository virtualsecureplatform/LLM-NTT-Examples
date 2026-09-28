# N=512 SGen precision and bounded-error product search

This experiment extends the [exact NGen pre-route comparison](fhe512-preroute-example.md)
with complete SGen FFT products under the same N=512 negacyclic, near-full-range
signed 32-bit input and modulo-`2^32` output contract. Both input operands are
fresh; the external interface carries two coefficients per cycle. The SGen
compact backend performs a 1,024-point FFT product for each radix-16 digit
pair. Only pairs with digit indices summing below eight affect the low 32
output bits, leaving 36 digit products in the exact implementation.

The search sweeps 30 and 32 fractional bits and omits zero, one, or two
low-weight digit diagonals. Both precision settings have conservative leaf
FFT error below half an integer, so every included digit product rounds to
the exact integer result. Omission is the only approximation in these six
points. A 24-bit control is rejected before hardware screening because its
leaf error bound is about 30 integer units and does not certify that rounding.

The omitted-product error is bounded for **every** input within the declared
range: each negacyclic output coefficient has at most 512 terms per omitted
digit pair, each low nibble has magnitude at most 15, and a pair `(i,j)` has
weight `16^(i+j)`. The resulting absolute coefficient bounds are:

| Omitted low diagonals | Digit products | Worst-case torus-unit error |
| ---: | ---: | ---: |
| 0 | 36 | 0 |
| 1 | 35 | 115,200 |
| 2 | 33 | 3,801,600 |

The independent Python oracle subtracts exactly those digit-pair convolutions
from an arbitrary-precision schoolbook product before reducing modulo `2^32`.
RTL simulation checks every output beat against that oracle. Separately, the
report measures centered modular error against the exact product over dense
positive, alternating-extreme, and seeded random frames. The observed maximum,
RMS, bias, and tail counts are empirical; the bound above is analytical.
The 4,000,000-unit screening limit is exploratory. It is not an FHE operation's
noise margin or a decryption-failure guarantee.

Build and run the pinned Apptainer workflow from the repository root:

```bash
git submodule update --init --recursive
scripts/build_assurance_yosys.sh
scripts/build_llm_ntt_sif.sh --definition apptainer/fhe512-preroute.def \
  --output build/fhe512-sgen-precision.sif --skip-check
scripts/run_fhe512_sgen_precision.sh --output-dir build/fhe512-sgen-precision \
  --fractional-bits 30 32 --omit-low-diagonals 0 1 2 --timeout 1800
scripts/run_fhe512_sgen_precision.sh --output-dir build/fhe512-sgen-f24-control \
  --fractional-bits 24 --omit-low-diagonals 0
# The control exits with status 1 because certification rejects it.
python3 scripts/report_fhe512_sgen_precision.py \
  build/fhe512-sgen-f24-control/results.json \
  build/fhe512-sgen-precision/results.json \
  --output-md docs/measured-evidence/fhe512-sgen-precision.md \
  --output-csv docs/measured-evidence/fhe512-sgen-precision.csv \
  --evidence-file docs/measured-evidence/fhe512-sgen-precision.json
```

The [per-configuration table](measured-evidence/fhe512-sgen-precision.md),
[CSV](measured-evidence/fhe512-sgen-precision.csv), and
[evidence snapshot](measured-evidence/fhe512-sgen-precision.json) record
error, coarse Yosys cells, retained memory bits, register bits, latency,
frame interval, and products per 1,000 cycles. The Yosys script runs
`proc; flatten; memory_collect; stat` on the complete product RTL. It retains
inferred memories and therefore counts at a different level than the
memory-lowered NGen table in the preceding example; their cell totals should
not be compared directly.

All six certified points passed RTL simulation and Yosys screening. The
observed maximum error equaled the analytical bound for each omission depth.
The three 30-bit configurations form the measured Pareto frontier: omitting
one or two diagonals improves the frame interval from 505,844 to 491,807 or
463,733 cycles, respectively, while increasing the coefficient-error bound.
Those intervals correspond to 0.001977, 0.002033, and 0.002156 products per
1,000 cycles. Each variant still has 48,381 coarse cells and 2,984,560
retained memory bits because the RTL reuses the same FFT hardware and changes
only its serial schedule. At the same error and latency, 32-bit fractional
precision uses 81,920 additional memory bits and 1,038 additional register
bits, so it is dominated at this synthesis level. This sweep finds a
latency/error tradeoff, not a resource/error tradeoff.

For a like-for-like resource reference, the
[NGen comparison snapshot](measured-evidence/fhe512-sgen-ngen-comparison.json)
re-screens two existing exact NGen products using the **same** memory-collected
Yosys script:

| Generator and architecture | Coarse cells | Retained memory bits | Latency cycles | Frame interval cycles |
| --- | ---: | ---: | ---: | ---: |
| NGen streamed, 2 lanes, Shoup | 18,963 | 3,192,708 | 8,067 | 3,390 |
| NGen stage-parallel, 2 lanes, Montgomery | 656,424 | 591,360 | 1,818 | 521 |
| SGen compact, 2 lanes, 30-bit exact | 48,381 | 2,984,560 | 511,711 | 505,844 |

The NGen latency and frame intervals come from their earlier verified product
campaigns; the coarse resource counts above were recomputed from those exact
RTL files. Generic cells, memory bits, and multipliers are separate screening
measures, not U280 LUT/DSP/BRAM utilization. The serial SGen candidate is much
slower than either NGen reference at two lanes. A useful next architecture
experiment is to evaluate more digit-pair parallelism or a faster FFT backend
before committing to U280 routing. These results do not provide a
timing-qualified clock, products per second, or an FHE noise qualification.

The [common-pass NGen/SGen frontier](fhe512-common-frontier.md) extends this
two-reference comparison to all 40 verified NGen configurations in the
published pre-route grids.
