# Product DSE release validation

Validated on 2026-09-22. The aggregate release check passed. See the
[runnable guide](product-dse.md) for contracts, commands and qualification rules.

## Source and software checks

- NGen submodule: `a2e16e18ff125a129794b7bf8c1b4f49296fedf9`.
- SGen submodule: `bbfa20cdf26dfdda3478e15e37938288d7bef8b9`, published on `dse-product-contracts`.
- Fresh recursive checkout, generator builds, legacy Chisel RTL generation and the six-point product smoke run passed.
- 161 NGen tests, 148 SGen tests and 170 Python tests passed; no tests skipped.
- An SGen-only campaign passed with an absent NGen root. Unchanged-source resume was exercised.
- The N=64 compact FFT matched all intermediate bits and product outputs under both Icarus and Verilator.

The clean-checkout test used a temporary Git snapshot of the implementation.
The subsequent hardware-target change enables the existing input hold-repair
helper; product RTL and generator pins are unchanged. The ten product tests
were rerun after that change.

## Functional covering matrix

| N | Qualified | Duplicate RTL | Insufficient FFT precision | Functional failures |
| --- | --- | --- | --- | --- |
| 8 | 22 | 2 | 2 | 0 |
| 16 | 22 | 2 | 2 | 0 |
| 32 | 21 | 2 | 2 | 0 |
| 64 | 23 | 2 | 2 | 0 |
| 256 | 20 | 2 | 4 | 0 |

All 130 configurations were accounted for: 108 qualified, 10 duplicates and
12 rejected by the conservative numerical bound. Precision rejection is an
expected design-space result, not a passed correctness test.

## Routed product measurements

These results are for N=16, fresh signed coefficients in [-7,7], two external
lanes, Vivado 2023.2, `xcu280-fsvh2892-2L-e`, and an 8 ns clock. All six
representative configurations passed simulation and completed synthesis.
Four were selected for routing. Complete product engines, adapters, buffers
and primary-input identity LUTs are included in the resource counts.

| Backend | Route qualified | LUT | FF | DSP | BRAM | Latency (ns) | Products/s | WNS (ns) | Hold (ns) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NGen streamed | True | 5,967 | 5,762 | 14 | 6 | 1,816 | 1,373,626 | 0.936 | 0.020 |
| NGen fully-parallel | False | 53,482 | 30,813 | 367 | 0 | unqualified | unqualified | -1.823 | 0.042 |
| SGen full-throughput | True | 112,337 | 97,240 | 504 | 45 | 2,032 | 6,578,947 | 0.448 | 0.021 |
| SGen compact | True | 76,166 | 44,940 | 180 | 9 | 2,720 | 992,063 | 1.106 | 0.027 |

Among these routed points, the streamed NTT has lower area and latency, while
the full-throughput FFT trades more resources for higher product throughput.
They form the reported route frontier. The fully-parallel NTT misses setup
timing and is excluded. NGen stage-parallel and streamed PE=2 have synthesis
evidence only in this representative campaign. This is not an exhaustive
hardware search or a claim of superiority over AutoNTT.

The initial, unbuffered 4 ns diagnostic route missed NTT setup and input hold
timing. That campaign was stopped before all routes completed. The final
matched 8 ns campaign enables one stage of the existing primary-input
hold-repair helper for every design. No qualified 4 ns comparison is claimed.

FFT qualification is a conservative arithmetic-model error certificate plus
independent RTL tests, not a formal RTL equivalence proof. These are routed
fabric measurements, not board-level throughput measurements.

## Artifacts and reproduction

Generated artifacts are intentionally kept under the ignored `build/` tree:

- [Aggregate acceptance](../build/dse-release/release-report.json).
- [Matched hardware report](../build/dse-release/hardware-8ns/report.md).
- [Machine-readable hardware evidence](../build/dse-release/hardware-8ns/report.json).
- [Build, test and fresh-checkout evidence index](../build/dse-release/verification-summary.json).

The evidence index records the local tool paths used for validation. Icarus
12 was built in `build/tools`; the host's Verilator wheel needed a local
wrapper to supply its missing PCH make setting. These are environment tools,
not vendored source dependencies. Use installed tools on PATH for a new run:

```bash
git submodule update --init --recursive
python3 scripts/dse_release.py --stage all --output-dir build/reproduced-dse
```

The default driver uses input hold repair for both its 4 ns attempt and its
separate 8 ns fallback. Campaign manifests preserve source/tool identities,
and candidate records bind qualification to the RTL, test inputs and
implementation artifacts. Use a new directory after changing sources; resume
deliberately rejects a different source snapshot.
