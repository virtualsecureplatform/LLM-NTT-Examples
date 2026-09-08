# Compact Kyber storage

NGen's opt-in `-preset-backend compact` Kyber architecture replaces bulk
register-array copies with three logical coefficient buffers packed into two
physical RAM banks. The existing microcoded implementation remains available.

The workload uses sequential full-frame load, compute, and read phases. Host
transfers must not overlap computation or another host transfer in the compact
architecture, and a bank must be fully loaded after reset before use. RAM
contents before initialization are unspecified. These requirements appear in
the generated RTL, `preset_contract` metadata, and search configuration. They
match the existing preset benchmark's transaction sequence; they do not extend
the benchmark to arbitrary concurrent command combinations.

The physical bank is the XOR of address bits 7 through 1, and its row retains
bits 7 through 2 and bit 0. Every Kyber butterfly pairs addresses differing in
one of bits 1 through 7, so its operands use distinct physical banks. Logical
buffer pointers supply the high RAM-address bits. First-stage reads come from
the selected A/B buffer, while writes go to the spare buffer. Subsequent stages
read and write the spare buffer. Completion swaps logical pointers instead of
copying 256 coefficients. The other polynomial remains intact.

The seven-stage instruction decoder replaces the two 896-entry instruction
ROMs. Generation compares every decoded address and twiddle against the existing
forward/inverse microprogram and checks the bank split and pipeline dependency
distances. One twiddle table serves both directions; inverse normalization is
folded into the Montgomery constant by modular halving. Synchronous RAM outputs
feed the existing pipelined arithmetic without adding transaction cycles.

Validation includes the unchanged four-case preset oracle, compact-mode reset
aborts at twelve issue/retirement positions, and a new 16-operation test that
reuses both banks without reset or reload. The latter reuses the original
reference vectors and read helpers and checks the untouched bank after each
transform. `scripts/check_kyber_bank_reuse.py` snapshots RTL, test sources, and
vectors and saves compiler/test commands and input hashes.

The extended reuse test is additional NGen coverage. The extracted baseline
fails its early untouched-bank read at index 2; this is outside the original
four-case benchmark and is not treated as a baseline failure under that task's
existing contract. The original baseline remains qualified by its original
oracle. Its diagnostic is `build/kyber-extracted-bank-reuse-with-sources`.

The first separately banked version passes synthesis at 948 LUTs, 401 FFs,
two DSPs, three BRAM tiles, and WNS +0.365 ns at 4 ns
(`build/kyber-banked-portable-hardware`). It retains the original 1414 transaction
cycles. The denser two-bank version passes the reset and 16-operation checks
(`build/kyber-packed-bank-reuse`); the full preset/hardware campaign also passes at `build/kyber-packed-hardware`.
Its synthesis uses 628 LUTs, 223 FFs, two DSPs and one BRAM tile, with WNS
+0.704 ns at 4 ns and unchanged 1414 transaction cycles. Against the extracted
reference this saves 19.2% LUTs, 36.8% FFs and 60% BRAM tiles, at the cost of
one DSP. Synthesis hold is -0.075 ns; no routed result is claimed for either
compact version. The compact backend is integrated into main and included
alongside microcoded in `campaigns/kyber.json`.
The original compile failure remains under `build/kyber-banked-hardware`.

`build/kyber-storage-comparison` combines the extracted reference, the failed
unpipelined design, the register-array pipeline, separate-bank RAM storage, and
densely packed RAM storage. Recreate it in an empty output directory with:

```sh
python3 scripts/compare_preset_runs.py --campaign campaigns/kyber.json \
  --reports build/kyber-extracted-hardware-comparison/report.json \
            build/kyber-pipelined-hardware/report.json \
            build/kyber-banked-portable-hardware/report.json \
            build/kyber-packed-hardware/report.json \
  --output-dir build/kyber-storage-comparison
```

The importer checks workload, target, and RTL identity, records hashes of the
input reports and available implementation artifacts, and keeps failed points.
The extracted reference and packed NGen remain on the synthesis frontier because
of the DSP tradeoff. `campaigns/kyber-hardware.json` generates and measures the
current microcoded/compact choices with the same preset oracle and target.
