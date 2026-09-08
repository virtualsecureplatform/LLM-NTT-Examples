# Compact stream address emission

The isolated NGen branch `compact-stream-io` (`c531b18`) replaces affine stream
bank/row case tables with XOR expressions. The emitter derives an affine map
from binary basis addresses and then checks every original table entry. A
non-affine table retains the original case implementation. This preserves
custom-plan behavior and avoids assuming that every permutation is linear.

Capture writes, synchronous output prefetches, next-output reads, and output
lane selection use the compact expressions. Physical coefficient banks,
ports, buffering, arithmetic, and protocol state transitions are unchanged.
Generated case-item whitespace required a follow-up fix; the original failed
compilations remain under `build/compact-io-{forward,inverse}-validation`.

Ten focused Scala tests pass, including Icarus execution of all entries of
bit-reversed, folded-bank, incremented-counter, and constant expressions,
nonlinear fallback, and malformed table rejection. Eight complete generic
oracle configurations pass in
`build/compact-io-{forward,inverse}-spacing-validation`: N=256/q32, forward
and inverse, PE=1/2, stage groups=1/2, Montgomery reduction, four lanes. These
checks include stalls, saturation, and reset recovery. N=256/PE=2/group=1 RTL
is 138588 bytes in the forward direction and retains latency 791 and frame
interval 852 cycles.

The isolated N=128K/q32 forward check now passes the complete oracle suite
with externalized control ROMs. Compact generation reduces RTL from 163761740
to 83632815 bytes before externalization; after moving exact ROM words into
hex files, the core RTL is 104502 bytes. Verilator compiles the core check in
6.9 seconds and completes simulation in 15.0 seconds. These are simulator wall
times on this host, not hardware measurements.

The first diagnostic artifact (`build/compact-io-large-verilator-validation`)
checks the core directly and therefore omits the two-cycle registered boundary.
Use `build/compact-io-large-normalized-verilator-validation` for the normalized
result: latency 655528, frame interval 688293, eight main frames and full reset
recovery PASS. These metrics match those observed before the original Icarus
attempt timed out during its reset checks. The earlier incomplete Icarus and
signal-9 Verilator attempts remain failed evidence.

`scripts/run_fhe_verilator_matrix.py` runs singleton generic campaigns through
the same registered-boundary adapter and full Verilator oracle, with exact ROM
externalization. It snapshots the generator binary, records source/campaign/
helper hashes, checks executable inputs before each case, and saves generation
and verification outcomes separately. It does not inherit passes from another
campaign or claim hardware fit. An N=256 end-to-end smoke check precedes the
18-point matrix (16K/64K/128K, 32/54/64 bits, forward/inverse). A matched
N=256 synthesis run is also pending under `build/compact-io-synthesis256`.

After the live policy trial finished, the compact-address changes were integrated
into NGen main together with Kyber normalization and YATA converter sharing.
The combined build passes all 148 Scala tests. N=256 compact-address synthesis
passes with 5126 LUTs, 1887 FFs, 18 DSPs, four BRAM tiles, WNS +0.599 ns and
WHS +0.063 ns under the two-buffer target. Before compaction the same synthesis
target used 5101 LUTs, 1735 FFs and 22 DSPs. The compact version trades 25 LUTs
and 152 FFs for four DSPs; the full routed ablation is still running at
`build/ngen-integrated-compact-route256`.

The integrated compact design now passes routing in
`build/ngen-integrated-compact-route256`: 4904 LUTs, 1950 FFs, 18 DSPs, four
BRAM tiles, WNS +0.240 ns and WHS +0.006 ns, with unchanged 791-cycle latency
and 852-cycle frame interval. Against the original same-target route, this
trades 15 LUTs and 208 FFs for four DSPs. The updated three-generator artifact
is `build/comparison-threeway256-compact-routed`; all three still qualify.
