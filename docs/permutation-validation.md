# Permutation validation

The square `check_permutation_generators.py` suite compares NGen and SGen switch
networks at 2, 4, 8, 16, and 32 lanes, including consecutive frames and legal gaps.
The composed YATA tests cover use of SGen's square network inside a complete NTT.

`check_rectangular_permutations.py` adds a matrix-index oracle for SGen's
existing rectangular, memory-backed adapter. Run with:

```sh
python3 scripts/check_rectangular_permutations.py --output-dir build/rectangular-permutation-validation
```

All 12 nonsquare combinations of rows/columns from {2,4,8,16} pass with Icarus.
Each configuration receives six tagged matrices, a reset during partial capture,
transactions at the minimum interval, and additional gaps of 1, 2, and 7 cycles.
The checks compare every output lane and every `next_out` pulse against a
row-major to column-major matrix traversal. RTL/test hashes, generator binary
hash, source identity, commands and logs are recorded in the report directory.

The adapter exchanges spatial lanes and temporal cycles. For R rows and C
columns, it consumes R cycles of C lanes and emits C cycles of R lanes. First
output arrives R cycles after first input; the supported frame interval is
R+C cycles. Input must not overwrite storage during output serialization.
Consequently these components do not share the square network's uninterrupted
full-throughput contract, and their cycle counts are not directly comparable
without a measured width/protocol adapter.

Fixed-width SGen linear/stride networks, additional memory permutations, and
full-design resource comparisons remain unverified portions of the milestone.

`check_linear_permutations.py` now verifies fixed-width SGen stride networks at
(N,lanes,matrix columns)=(16,2,4), (32,4,4), (64,4,8), and (64,8,4), each with
single and dual RAM control. All eight cases pass in
`build/linear-permutation-contract-validation`. Each is checked for two epochs
of six matrices, continuous frames, legal gaps, and reset after an aborted
transaction with a 4N-cycle drain. Single-control gaps use the generated
minimum spacing; dual-control tests include one- and two-cycle gaps.

The advance `next` signal varies from one to four cycles across these designs.
The harness reads this interface declaration from generated RTL and records it,
while expected data comes from an independent matrix traversal. An earlier
harness assuming a universal two-cycle lead produced failures; those artifacts
remain under `build/linear-permutation-validation` and are harness failures,
not established SGen arithmetic/permutation faults.

## Full NTT composition

`campaigns/yata8x8-sgen-linear.json` selects a new bounded `sgen-linear`
permutation option. Its adapter replaces the packed square networks with
SGen dual-control stride RAMs, delays payload by the generated `next` lead,
and reconstructs frame-valid output. Payload registers and control logic are
part of the composed RTL. It retains the uninterrupted-frame contract; it does
not add ready/valid stall support. This option is currently legal only for the
small YATA 8x8 preset, whose complete NTT oracle has been checked.

`build/yata8x8-sgen-linear-validation` passes the unchanged forward/inverse
preset tests. The measured worst transaction is 96 cycles (8 input, up to 80
wait, 8 output); sustained initiation interval remains unmeasured by this legacy
preset harness. The generated NGen timing metadata is retained as declared
metadata, not substituted for this measured adapter-inclusive transaction.

`campaigns/yata8x8-permutation-comparison.json` now evaluates NGen switches,
SGen switches, and SGen stride RAMs under the same preset workload and target,
including full-design synthesis. Its initial campaign is in progress at
`build/yata8x8-permutation-comparison`; no resource advantage is claimed yet.
