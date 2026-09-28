# N=512 NGen pre-route grid

The NGen campaign generates complete negacyclic products over the 32-bit torus.
Each configuration runs twelve complete-product frames against an independent
integer schoolbook oracle, then receives a coarse Yosys synthesis pass. The
runner records the analytical per-coefficient error bound, observed error,
generic cells, latency cycles, frame interval cycles, RTL hash, and failures.
The default approximation rounds output coefficients to multiples of 16,
introducing a bound of eight torus units. This is an exploration control, not
an FHE noise budget.

Set up the pinned NGen assembly, Yosys 0.50, and Apptainer image as described
in the [root README](../README.md). Run a small smoke grid first:

```bash
scripts/run_fhe512_preroute.sh --n 16 --bound 7 \
  --output-dir build/fhe512-smoke
python3 scripts/report_fhe512_preroute.py --output-dir build/fhe512-smoke
```

The covering grid spans streamed and stage-parallel backends, lane counts,
PE counts, radix and stage grouping, Barrett/Montgomery/Shoup reduction,
baseline/f300 profiles, and selected rounded-output variants. The transpose
boundary can be `indexed` or `switch`:

```bash
scripts/run_fhe512_preroute.sh --grid covering --n 512 \
  --transposes indexed switch --timeout 1200 \
  --output-dir build/fhe512-covering-new
python3 scripts/report_fhe512_preroute.py \
  --output-dir build/fhe512-covering-new
```

Use `--resume` with the same output directory after interruption. Use
`--configuration-names` to select named points, `--quant-bits` to change output
rounding, and `--bound` for a smaller input range. The `switch` choice is a
rate-preserving buffered rectangular transpose at N=512. A stage-parallel
point can require far more synthesis time than a streamed point.

The [common NGen/SGen frontier](fhe512-common-frontier.md) is the primary
published comparison. Its 40 NGen rows combine a 28-point reduction matrix
([CSV](measured-evidence/fhe512-reduction-matrix.csv)) and 12 distinct
covering-grid points ([CSV](measured-evidence/fhe512-covering-table.csv)).
The matching pre-route RTL and full campaign results are build artifacts, so
re-running `scripts/run_fhe512_common_synth.sh` for the **historical** snapshot
requires those exact artifacts and verifies their hashes. A fresh grid may
produce different RTL when the generator changes; it should be treated as a
new campaign, not silently substituted for the published evidence. The
checked-in [common evidence JSON](measured-evidence/fhe512-common-frontier.json)
preserves the screened metrics and source hashes.

Yosys numbers are rough generic-resource measures before U280 mapping and
place and route. Latency and interval are cycle counts, with no routed clock
frequency. Approximation bounds do not establish decryption reliability for
any particular FHE operation.
