# LLM-NTT Examples

This repository explores hardware design choices for N=512 negacyclic polynomial
multiplication with near-full-range signed 32-bit coefficients and outputs modulo
`2^32`. NGen generates NTT products; SGen generates FFT products. The current
centerpiece is a **pre-route grid search** that checks complete-product RTL,
measures coarse Yosys resources, and compares arithmetic error, latency, and
sustained frame interval. It does not claim U280 utilization or timing.

Start with the [combined NGen/SGen frontier](docs/fhe512-common-frontier.md) and
its [per-configuration table](docs/measured-evidence/fhe512-common-frontier.md).
The checked-in evidence contains 40 NGen and 6 SGen screened configurations,
with separate columns for backend, lanes, PE count, radix, reduction algorithm,
transpose boundary, precision, and approximation controls. The full RTL hashes
and source campaign identities remain in the machine-readable
[CSV](docs/measured-evidence/fhe512-common-frontier.csv) and
[JSON](docs/measured-evidence/fhe512-common-frontier.json).

## Layout

- `architecture_search/`: workload contract, generators, RTL construction,
  independent oracles, numerical analysis, and source identity checks.
- `scripts/`: NGen/SGen campaigns, common Yosys pass, reports, and build tools.
- `apptainer/`: the small pinned pre-route runtime image definition.
- `docs/`: experiment instructions and checked-in measured evidence.
- `tests/python/`: retained model and report tests.
- `third_party/`: pinned NGen, SGen, AutoNTT, and TFHEpp submodules.

Historical experiments and implementations remain recoverable from Git history.

## Complete multiplication study

The [polynomial multiplication studies](docs/polynomial-study.md) expand the comparison
to full-width, byte, and ternary operands, FFT precision and digit omissions,
NTT architectures, and separate output-rounding controls. Start with
`python3 scripts/polynomial_study.py --dry-run`; the default specification is
`studies/torus512.json`. New evidence is written to ignored build directories.
For a bounded 12-configuration demonstration with the same validation pipeline,
run `scripts/run_polynomial_study.sh --spec studies/torus-demo.json --output-dir build/polynomial-study-demo`.
The completed [results tables and tradeoff plots](docs/results/polynomial-results.md)
include all 171 qualified N=512 designs and all 12 demo designs, with CSV snapshots.
The [full-throughput FFT extension](studies/torus512-full-fft.json) adds two/four-lane
FFT designs at N=512; its separate campaign and merged reporting are described in the study guide.

## Run a new grid

From the repository root, with Apptainer, `sbt`, and native build dependencies:

```bash
scripts/build_generators.sh
scripts/build_assurance_yosys.sh
scripts/build_fhe512_image.sh
scripts/run_fhe512_preroute.sh --n 16 --bound 7 \
  --output-dir build/fhe512-smoke
scripts/run_fhe512_preroute.sh --grid covering --n 512 \
  --output-dir build/fhe512-covering-new
python3 scripts/report_fhe512_preroute.py \
  --output-dir build/fhe512-covering-new
```

The N=16 run checks the toolchain quickly. N=512 synthesis is much slower,
especially for stage-parallel designs; interrupt and restart a campaign with
`--resume`. The [NGen campaign guide](docs/fhe512-preroute-example.md) describes
the grid controls. The [SGen guide](docs/fhe512-sgen-precision.md) covers FFT
precision and omitted digit products. The [combined frontier guide](docs/fhe512-common-frontier.md)
explains the matched Yosys pass and how its historical source RTL is identified.

Run the retained Python checks with `python3 -m unittest discover -s tests/python -q`.
The checked-in snapshots are evidence from completed campaigns, while new
runs write to ignored `build/` directories.
