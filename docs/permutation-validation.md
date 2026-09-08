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
