# Prefetched PE control ROM

NGen `1382267` selects synchronous block ROM for static radix-2 PE control tables
with at least 1024 operation bundles. Smaller, writable, and fused-radix tables
retain their previous implementation. The generator initializes the same packed
records; this changes storage and access timing, not the operation schedule.

While execution is inactive the ROM fetches record zero. An issue fetches the
next record, which remains registered through stage drains. The next stage thus
starts with its first record already available. The final issue does not read
past the table. The read has one address port and no reset on the data register;
execution/reset control prevents consumption before initialization.

This targets the 114739-LUT N=16384/q54 synthesis result recorded in
`build/ngen-fhe16k54-two-buffer-fabric`. That result's critical setup path crosses
the wide Montgomery multiplier; this ROM change does not claim to fix it.
Block RAM replaces logic storage, so resource improvement must be measured
across both LUT and BRAM counts.

The final implementation passed the unchanged full generic oracle in both
forward and inverse directions:

| Evidence directory | Frames | First-output latency | Initiation interval |
| --- | ---: | ---: | ---: |
| `build/block-control-final16k54-forward` | 8 | 69773 | 73866 |
| `build/block-control-final16k54-inverse` | 8 | 69773 | 73866 |

These metrics exactly match the original forward control-ROM implementation.
The oracle includes input gaps, saturated frames, output stalls/stability and
reset recovery. All 150 Scala tests pass. The first complete Scala invocation
lacked `iverilog` on PATH and failed two tool-dependent tests; after sourcing
`/tmp/check-native-tools.sh`, the full suite passed without test changes.

`campaigns/fhe16k54-block-control.json` runs the same field, lanes, PE count and
4 ns fabric contract through simulation and synthesis. Its initial measurement
is queued in `build/ngen-fhe16k54-block-control`; physical inference, resources,
and setup timing remain unverified until that vendor run completes. The
previous routed campaign is retained as the comparison baseline.
