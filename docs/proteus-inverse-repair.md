# Proteus MDC inverse repair

The isolated Proteus adapter supports `--fix-mdc-inverse-rom` for merged
negacyclic MDC OP1. The upstream source tree is unchanged. The generated-tree
manifest records the option and before/after hashes of every compatibility edit.
Results using this option must be identified as a modified Proteus baseline.

The original N=256 inverse failed the independent impulse vector. Its inverse
ROM path included an extra output register, causing the first multiplication
to use the ROM's default value instead of its encoded twiddle. The repair uses
`intt ? data_itw : data_out` at the ROM wrapper output, aligning inverse twiddles
with the registered subtraction while retaining the forward path.

The adapter also replaces the Montgomery multiplier's potentially out-of-range
output slice with a left shift truncated to the declared output port width.
This removes a Verilator C++ compilation failure for the tested 64-bit field.
It is recorded separately from the inverse arithmetic repair.

Fresh normalized stream checks, including eight oracle frames, stalls, and
reset, passed with both edits:

| Artifact under `build/` | Latency (cycles) | Initiation interval (cycles) |
| --- | ---: | ---: |
| proteus-mdc-forward256-portable | 740 | 802 |
| proteus-mdc-inverse256-portable | 748 | 810 |
| proteus-mdc-inverse64-portable | 924 | 986 |

The first two use q=2147484161; the third uses q=9223372036854793729.
These are functional and cycle results, not routed measurements. Original
failing artifacts remain historical evidence and are not promoted.

`check_proteus_baseline.py --simulator icarus` enables a diagnostic alternative
to the default Verilator. It does not imply all upstream RTL is Icarus-compatible:
the tested wide MDC design still has upstream expression/elaboration failures.
