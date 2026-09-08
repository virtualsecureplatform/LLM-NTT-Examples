# Shared fabric-interface timing contract

`campaigns/threeway256-fabric.json` fixes the module-level timing environment
before the next matched implementation runs. It uses the U280, Vivado 2023.2,
and a 4 ns clock. All generators use the same registered ready/valid boundary.

| Constraint | Value |
| --- | --- |
| OOC clock source site | BUFGCE_X0Y0 |
| I/O clock reference | input_full_reg/C |
| Minimum input arrival | 0.5 ns |
| Maximum input arrival | 1.0 ns |
| Output hold requirement | 0.0 ns |
| Output setup requirement | 1.0 ns |

These values define a conditional integration contract: external fabric logic
must deliver all inputs, including reset and flow control, within that arrival
window relative to the boundary clock, and accept outputs under the listed
requirements. They are not measurements of U280 board wiring, host transfers,
or an existing shell. A board integration needs its own validated constraints.

The reference-pin option uses the clock at the registered module boundary;
AMD documents this mechanism in [set_input_delay](https://docs.amd.com/r/2023.1-English/ug835-vivado-tcl-commands/set_input_delay).
The previous port-referenced clock model compared fabric data against the
pre-distribution clock edge. Earlier diagnostic runs with zero or 0.2 ns
minimum arrival remain failed evidence under their own constraints. The new
contract does not retroactively promote them.

Every new run still checks setup, hold, and complete routing. Constraints apply
to all non-clock input ports and all output ports. No reset false path, hold
waiver, or register-only timing gate is added. The same target object must match
exactly when importing NGen, OpenNTT, and Proteus measurements.

## Optional physical output buffers

The unbuffered N=256 Montgomery fabric run completed routing with WNS +0.276 ns
and WHS -0.052 ns (`build/ngen-mont7-fabric256`), so it remains excluded.
The worst hold path is an output register to `out_valid`; the reported data
path has no routing delay. The remaining failure is at the output boundary.

`campaigns/threeway256-buffered-fabric.json` keeps every timing requirement
above and enables `target.output_hold_buffers`. After synthesis,
`scripts/insert_output_hold_buffers.tcl` inserts a preserved identity LUT on
each output bit, giving implementation a physical data path. These LUTs count
in utilization, add no cycles, and are recorded in `output_hold_buffers.txt`.
The NGen experiment in `build/ngen-mont7-output-buffers256` passed synthesis;
routed results were still pending when this change was documented. This is an
optional physical implementation experiment, not a demonstrated timing fix.
External comparisons must use the identical target, including this option.
