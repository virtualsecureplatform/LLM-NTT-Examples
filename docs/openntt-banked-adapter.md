# OpenNTT banked stream adapter

The initial 16K/q54 routed campaign failed during synthesis because the normalized
adapter wrote four coefficients per cycle into one flat array and read it
asynchronously. Vivado could not infer the 884736-bit input memory and refused
to dissolve it into registers. The failed measurement remains in
`build/openntt-fhe16k54-two-buffer-fabric`; it is not evidence of OpenNTT's
hardware performance.

The adapter now has one physical input and output bank per stream lane. Each
bank has one write port and a synchronous read. Capture writes the lane banks
in parallel; scalar core loading selects the appropriate registered bank output.
Core readback writes one output bank, and stream output reads all banks in
parallel. Output data holds during backpressure. Memory contents are not reset;
control requires full capture and core readback before consuming each buffer.

A prefetch state before scalar loading and another before stream output add two
cycles per transform. The exact modulus, root, ordering, two coefficient buffers,
scalar core port, external width and registered ready/valid boundary are retained.
No change to the upstream arithmetic core is involved in this adapter repair.

Fresh generated baselines pass the unchanged full stream oracle:

| Evidence directory | Workload | Latency | Initiation interval | Frames |
| --- | --- | ---: | ---: | ---: |
| `build/openntt-banked-forward256` | N=256/q32 forward | 1134 | 1196 | 8 |
| `build/openntt-banked-inverse256` | N=256/q32 inverse | 1135 | 1197 | 8 |
| `build/openntt-banked-forward16k` | N=16384/q54 forward | 94257 | 98351 | 8 |

The suite checks arithmetic, ordering, saturated frames, input gaps, output
stalls/stability and mid-frame reset. All 120 Python tests also pass.
`build/openntt-banked16k54-route` now measures the verified 16K artifact using
`campaigns/fhe16k54-two-buffer-fabric.json`. Its resource and timing outcome is
pending; simulation does not by itself prove physical RAM inference or closure.

Reproduce a baseline with `scripts/prepare_openntt_baseline.py`, then run
`scripts/check_openntt_baseline.py --stream` before
`scripts/measure_external_ntt.py --stage route`. Use new directories so older
adapter measurements and failed tool runs remain intact.

The fresh 16K route completes and passes: LUT 5961, FF 7198, DSP 68, BRAM 74,
setup WNS +0.275 ns and hold +0.010 ns. This verifies that the revised adapter
avoids the earlier RAM-inference failure. The full matched report is
`build/comparison16k54-banked-routed`, including failed NGen timing evidence.
OpenNTT is the only qualified routed point in that two-design comparison;
NGen's lower simulated cycle count does not qualify its 250 MHz throughput.
