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

A fresh isolated N=128K/q32 generation and Verilator check with externalized
control ROMs is running under `build/compact-io-large-generation` and
`build/compact-io-large-verilator-validation`. The generated candidate inherits
no correctness status from the earlier design. Large-transform compilation,
correctness, and hardware-resource benefits remain unproven. The original
Icarus longer-budget check remains independent under
`build/fhe-icarus-extended-n131072-q32-forward`.

The branch is not merged into the generator used by the active live policy
trial. Integrate only after that trial finishes and after reviewing the large
checks and matched hardware results.
