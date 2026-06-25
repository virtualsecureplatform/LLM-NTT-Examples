# kyber-polmul-hw Reference RTL

This directory contains the PE1 CRYSTALS-Kyber polynomial multiplication RTL
reference copied from the sibling `kyber-polmul-hw` checkout.

The checked-in task uses `pe1/KyberHPM1PE.v` as the top and preserves the
original PE1 FNTT/INTT vector files under `pe1/test_pe1`. The source file
headers dedicate the RTL to the public domain via CC0:

<http://creativecommons.org/publicdomain/zero/1.0/>

The repository harness does not use the original Verilog testbenches directly.
Instead, `tests/cpp/kyber_pe1_reference_test.cpp` drives the same load, start,
done, and read protocol through Verilator so Kyber fits the same
`scripts/evaluate_candidate.sh` flow as HOGE and YATA.
