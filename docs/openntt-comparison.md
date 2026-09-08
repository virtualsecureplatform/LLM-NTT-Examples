# OpenNTT comparison evidence

The first workload-matched comparison uses N=256, q=2147484161, a negacyclic
forward transform, and four natural-order input/output lanes. Both generators
pass the same arbitrary-precision oracle and streaming checks. These are
simulation measurements for the listed configurations, not a claim that NGen
outperforms the best possible OpenNTT design or published routed implementations.

| Generator | PE organization | First-frame latency (cycles) | Maximum measured frame interval (cycles) |
| --- | --- | ---: | ---: |
| NGen | 2 PEs, 1 stage group | 755 | 816 |
| NGen | 2 PEs/group, 2 groups | 886 | 540 |
| NGen | 2 PEs/group, 4 groups | 1148 | 402 |
| OpenNTT RoutOpt | 2 PEs | 1132 | 1194 |
| OpenNTT MemOpt | 2 PEs | 1132 | 1194 |

The external boundary matters. OpenNTT's kernel computes this transform in 533
cycles, excluding host transfers. The normalized adapter includes its scalar
host port, two frame buffers, ordering conversion, and ready/valid registers.
NGen accepts its lanes through its native stream. The end-to-end comparison
counts all of these resources and cycles; kernel-only timings must not be
compared to complete streaming transactions. Area and frequency measurements
are still required to decide the hardware tradeoff.

The local report is `build/comparison-openntt-ngen256/report.json`, with commands,
source identities, candidate hashes, and verification artifacts. The checked-in
`campaigns/openntt-overlap256.json` specifies the exact field/root and candidate
space. Use `prepare_openntt_baseline.py`, `check_openntt_baseline.py --stream`,
and `compare_openntt_ngen.py` as documented in `architecture-search.md` to reproduce.

Additional completed validation:

- OpenNTT N=256/q32 inverse, two PEs: physical-memory and normalized-stream oracle
  checks pass. Its compute-only timing is 534 cycles.
- OpenNTT N=16K/q54 forward, two PEs: the normalized stream passes the independent
  oracle, stalls, and resets; latency is 94,255 cycles and maximum frame interval
  is 98,349 cycles. Under the same field, four-lane interface, and two-PE
  configuration, NGen measures 69,713 cycles and a 73,806-cycle frame interval.
  The matched report is `build/comparison-openntt-ngen16k54/report.json`; this is
  still a cycle comparison without an area or routed-frequency conclusion.
- A diagnostic N=256/q16 RoutOpt configuration fails the arithmetic oracle even
  after host load/readback succeeds. It remains ineligible. This is not silently
  generalized to the validated 32/54-bit cases.

Portability fixes are applied only to isolated generated trees and recorded as
before/after hashes. The fixes name inactive custom-backend module instances,
retain ROM filenames as strings in Verilator, and size large modulus literals.
No upstream arithmetic or memory schedule is replaced by an oracle.

Routed comparison remains open. The earlier NGen hold failure was traced to an
input-port-to-boundary-register path with zero minimum input delay. Vivado also
reported an unset OOC clock-source property. New target fields make the assumed
clock source and input/output timing contract explicit. Reusing older reports
under new constraints would be invalid; new implementation runs are required.

The first explicit-clock/I/O diagnostic route also failed hold (−1.589 ns),
while setup slack was +1.035 ns. The clock-source property materially changes
clock insertion delay, so the assumed interface timing needs further diagnosis.
The failure remains excluded; no constraint change retroactively promotes it.
