# Realistic NTT benchmark suite, version 1

The suite extends NGen evaluation to paper-sized FHE kernels, the actual
Microsoft SEAL CKKS example, Goldilocks transforms and standard PQC fields.
[All 22 generic RTL checks pass](measured-evidence/realistic-v1/validation.json).
All eight captured SEAL prime/direction samples also pass through NGen RTL.
The dedicated ML-KEM preset passes its forward/inverse reference checks and
four complete polynomial-product checks with host quadratic multiplication.
These are functional results; no new synthesis or routed performance is claimed.

## Workloads

| Family | N | Modulus | Role |
| --- | ---: | --- | --- |
| FHE small | 4096 | Exact generated 32-bit prime | Development |
| FHE wide | 4096 | Exact generated 60-bit prime | Development |
| SEAL CKKS | 8192 | Four actual primes, widths [60,40,40,60] | Development/application trace |
| FHE medium | 16384 | Exact generated 54-bit prime | Held-out PPA evaluation |
| FHE large | 65536 | Exact generated 54-bit prime | Held-out PPA evaluation |
| Goldilocks | 1024 and 65536 | 18446744069414584321 | Extension, cyclic NTT/INTT |
| ML-DSA | 256 | 8380417, primitive 512th root 1753 | Extension, full negacyclic NTT |
| ML-KEM | 256 | 3329 | Extension, dedicated incomplete NTT |

The FHE sizes/widths are anchored to AutoNTT Tables II/IV and its comparisons
with OpenNTT and Proteus. The exact benchmark primes are generated
reproducibly; matching size/width does not imply matching a paper's exact prime
or reproducing its performance. Goldilocks 64K is our proposed scale-up.

Sources: [AutoNTT](https://zhenman.github.io/files/C45-FCCM2025-AutoNTT.pdf),
[OpenNTT](https://github.com/flokrieger/OpenNTT),
[Proteus](https://eprint.iacr.org/2023/267.pdf),
[SEAL 4.1.2 example](https://github.com/microsoft/SEAL/blob/119dc32e135cb89c1062076a69310d4413ebc824/native/examples/5_ckks_basics.cpp),
[FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf),
[FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf).

Every generic field has forward and inverse campaigns with exact decimal q,
root and psi strings. FHE and ML-DSA use negacyclic transforms; Goldilocks uses
cyclic transforms. Generic boundaries use canonical residues, natural ordering
and N^-1 inverse normalization. ML-DSA therefore needs ordering conversion when
compared with a bit-reversed FIPS implementation. A separate sparse schoolbook
convolution checks the mathematical polynomial-product oracle at every field.

[The suite manifest](../campaigns/realistic-v1/suite.json) links 22 validation
campaigns, 22 architecture-search templates and one ML-KEM preset campaign.
The search spaces vary PE count, radix, stage grouping and modular reduction.
Validation uses one explicit PE=2/radix=2/Montgomery/group=1 architecture per
field/direction, with four coefficients per interface beat. This establishes
coverage for that configuration, not all architectures in the search space.

## Actual CKKS trace and cross-library validation

SEAL is pinned to commit `119dc32e135cb89c1062076a69310d4413ebc824` (4.1.2).
The capture builds a separate instrumented copy, preserving the example's
arithmetic and API-call order. It records 386 actual NTT/INTT calls, labeled by
API phase, including key generation, encoding, encryption, evaluation and
decoding. It samples one operand/result pair per prime and direction.

The [ordered chain](measured-evidence/realistic-v1/seal-chain.json) is exported
by calling SEAL's own `CoeffModulus::Create` and reading its NTT tables:

| Chain position | Prime | Purpose |
| --- | ---: | --- |
| 0 | 1152921504606748673 | 60-bit ciphertext prime |
| 1 | 1099510890497 | 40-bit ciphertext prime |
| 2 | 1099511480321 | 40-bit ciphertext prime |
| 3 | 1152921504606830593 | 60-bit special key-switching prime |

The campaign names `ckks8k-prime0` through `prime3` sort primes numerically;
these indices are **not** chain positions. Exact q values provide the mapping.
The special prime is not treated as an ordinary active ciphertext limb.
The trace preserves actual calls as levels and operations change; it does not
assume every operation executes four identical limbs or two forward transforms
plus one inverse transform.

All eight SEAL samples match the independent integer oracle after lazy-residue
normalization and bit-reversal conversion. They then match NGen RTL using the
captured SEAL outputs directly as expected values. The existing compiled RTL
testbench repeats each sample under its gap/backpressure/reset scenarios;
original matrix vectors and evidence are preserved. This is sample-level RTL
cross-validation, not execution of the complete CKKS application on FPGA.

Published evidence:

- [Complete call trace and sample hashes](measured-evidence/realistic-v1/seal-trace.json)
- [Captured operands/results and event file](measured-evidence/realistic-v1/seal-samples.zip)
- [NGen versus captured SEAL samples](measured-evidence/realistic-v1/seal-rtl.json)
- [Generic validation manifest](measured-evidence/realistic-v1/validation-manifest.json)
- [ML-KEM preset checks](measured-evidence/realistic-v1/mlkem-validation.json)
- [ML-KEM polynomial-product checks](measured-evidence/realistic-v1/mlkem-products.json)

SEAL's randomized key/encryption material makes fresh operand samples vary.
The published samples are fixed and independently replayable. The trace is a
workload sequence and mix; it does not encode a complete memory-dependency
graph, model all FHE operations, or establish end-to-end application latency.

## ML-KEM scope

There is no primitive 512th root modulo 3329. The generic full-negacyclic adapter
rejects that field, and the suite uses the dedicated compact Kyber preset.
The four product cases include zero, wraparound, maximum residues and random
polynomials. NGen RTL computes both forward transforms and the inverse; the
host performs FIPS-style multiplication modulo each quadratic factor. Results
match an independent O(N^2) negacyclic schoolbook product. This does not claim
an RTL base multiplier or a complete ML-KEM implementation.

## Reproduction

From the framework repository, with the native simulator tools on PATH:

```sh
git clone --branch v4.1.2 --depth 1 https://github.com/microsoft/SEAL.git build/seal-source
python3 scripts/capture_seal_ntt_trace.py --seal-source build/seal-source --output-dir build/seal-capture
python3 scripts/export_seal_chain.py --capture-dir build/seal-capture --output-dir build/seal-chain
python3 scripts/make_realistic_benchmarks.py --seal-trace build/seal-capture/results.json --output-dir build/realistic-suite
python3 scripts/run_fhe_verilator_matrix.py --campaign-dir build/realistic-suite/validation --ngen-root ../NGen --output-dir build/realistic-validation --timeout 3600
python3 scripts/check_seal_rtl_samples.py --capture-dir build/seal-capture --matrix-dir build/realistic-validation --output-dir build/seal-rtl-check
python3 scripts/search_architectures.py --campaign build/realistic-suite/preset/mlkem256.json --ngen-root ../NGen --output-dir build/mlkem-validation --mode run
```

Run `scripts/check_kyber_polynomial_product.py --record <candidate-record.json>
--output-dir <fresh-directory>` on the correct ML-KEM candidate. The capture
requires CMake (`cmake3`), a C++17 compiler and the pinned source. Optional SEAL
GSL, compression and HEXL dependencies are disabled; no system install is needed.
All commands require fresh output directories to preserve earlier attempts.

To verify the published SEAL samples without building SEAL:

```sh
python3 -m zipfile -e docs/measured-evidence/realistic-v1/seal-samples.zip build/published-seal-samples
python3 scripts/verify_seal_trace.py --report docs/measured-evidence/realistic-v1/seal-trace.json --samples-dir build/published-seal-samples
```

## Search and measurement protocol

Use the `search/` templates with the existing architecture-search entry point.
Before a measured policy study, freeze explicit resource caps and give every
policy identical caps, target, evaluation count and wall-time budget. Templates
carry the same 4 ns U280 conditional fabric contract and two output hold buffers;
they deliberately contain no invented PPA metrics or measured frontiers.
Hardware comparisons must also match transform type, exact field, direction,
ordering and interface bandwidth.

Tune on 4K and CKKS cases. Freeze policy settings before observing 16K/64K PPA.
The completed held-out correctness checks are coverage tests, not policy
training observations. Compare single-frame latency, measured frame interval,
resource usage, and throughput including a stated transfer model. A simulator
cycle count alone cannot establish 250 MHz operation. Require completed routing
and nonnegative setup/hold for routed qualification, and report available margin.

The earlier six-candidate N=128 LLM frontier result is retained separately.
This suite has no complete measured PPA pool yet, so it does not report frontier
recall or claim improved search quality on these larger workloads.
