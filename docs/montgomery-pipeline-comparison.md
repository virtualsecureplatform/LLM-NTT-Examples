# Montgomery pipeline comparison

The 256-point, 32-bit exact-field campaign exposed a 7.397 ns estimated
register-to-register path in NGen's three-cycle butterfly. The final stage
combined correction multiplication, the carry sum, modular subtraction, and
butterfly arithmetic. At the 4 ns U280 target, all three stage-group choices
failed synthesis setup timing (WNS approximately -3.447 ns).

NGen now uses seven stages for Montgomery arithmetic, retaining one operation
per cycle. Operand preparation, each multiplication, the carry sum, canonical
correction, and the final butterfly operation have separate registers. Valid
bits and tags travel with operands; reset cancels every in-flight operation.
Barrett and Shoup retain their existing pipelines. This change applies to
radix-2 PEs; fused higher-radix datapaths are separate implementations.

For PE=2 and one stage group, measured synthesis changes are:

| Metric | Three-cycle pipeline | Seven-cycle pipeline |
| --- | ---: | ---: |
| LUT | 5216 | 4841 |
| FF | 1688 | 1735 |
| DSP | 22 | 22 |
| BRAM tiles | 4 | 4 |
| Estimated setup slack at 4 ns | -3.447 ns | +0.582 ns |
| First-frame latency, including stream boundary | 755 cycles | 791 cycles |
| Maximum measured frame interval | 816 cycles | 852 cycles |

These are synthesis estimates and verified RTL cycle measurements, not routed
frequency or board results. The two-group design also passes estimated setup
with WNS +0.582 ns, 8890 LUTs, 3079 FFs, 44 DSPs and eight BRAM tiles. The four-group design passes with WNS +0.582 ns, 16,500 LUTs, 5761 FFs,
88 DSPs and 16 BRAM tiles. Full
routing checks are still required for any hardware performance claim.

Validation includes 145 Scala tests; independent operator arithmetic at 5-,
32-, 54-, and 64-bit widths with exact latency, bubbles, tags and reset;
forward N=256/q32 and inverse N=256/q64 at one/two/four stage groups; and the
N=16384/q54 forward streaming oracle with stalls and mid-frame resets.
The final metadata recheck matches first-output latency and frame interval
for all three 256-point designs and confirms identical generated RTL hashes
before and after the metadata correction.

The metadata correction accounts for output prefetch, maximum frame-admission
spacing, and two-cycle beat spacing between buffered stage groups. The raw
latencies are 789/920/1182 cycles and admission intervals 852/560/414 cycles
for one/two/four groups; the measured common external boundary adds two cycles.

Evidence directories:

- `build/ngen-threeway256-synthesis`: original arithmetic, all setup failures.
- `build/ngen-mont7-threeway256`: revised arithmetic and matched synthesis.
- `build/ngen-mont7-metadata`: corrected declared timing checked against simulation.
- `build/ngen-mont7-inverse64` and `build/ngen-mont7-fhe54`: wider oracle checks.
- `build/ngen-mont7-route256`: fresh routing campaign; inspect its reports before claiming closure.

Reproduce the synthesis comparison using `campaigns/threeway256-synthesis.json`
and `scripts/search_architectures.py`. `NGen/scripts/test_pipelined_butterfly.py`
runs the independent operator regression with Icarus Verilog.

The combined report is `build/comparison-threeway256-mont7`. Synthesis
frontiers include throughput as well as latency and resources, retaining
buffered pipelines that trade additional area for a shorter frame interval.
The underlying clock-derived throughput is an estimate at the synthesis stage;
only passing route evidence can establish the routed comparison.
