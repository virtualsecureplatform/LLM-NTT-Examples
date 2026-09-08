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

Correction: the initially reported `block-control-final16k54-*` campaigns used
an older assembled `ngen.bat`, despite newer Scala source. Their RTL still has
distributed ROM, so those runs do **not** validate this optimization. The queued
`ngen-fhe16k54-block-control` synthesis was stopped before vendor execution;
`invalidated.json` preserves the reason. Source identity alone does not prove
executable freshness.

A clean detached checkout at `/tmp/ngen-block-control-ablation`, revision
`1382267`, has now been built with `sbt assembly`. Corrected oracle runs use
`build/block-control-rebuilt16k54-{forward,inverse}` and matched synthesis uses
`build/ngen-fhe16k54-block-control-rebuilt`. The following table records the
**older executable's** metrics and is retained only as the cycle baseline:

| Evidence directory | Frames | First-output latency | Initiation interval |
| --- | ---: | ---: | ---: |
| `build/block-control-final16k54-forward` | 8 | 69773 | 73866 |
| `build/block-control-final16k54-inverse` | 8 | 69773 | 73866 |

These metrics are from the original forward control-ROM implementation.
The oracle includes input gaps, saturated frames, output stalls/stability and
reset recovery. All 150 Scala tests pass. The first complete Scala invocation
lacked `iverilog` on PATH and failed two tool-dependent tests; after sourcing
`/tmp/check-native-tools.sh`, the full suite passed without test changes.

`campaigns/fhe16k54-block-control.json` runs the same field, lanes, PE count and
4 ns fabric contract through simulation and synthesis. Its initial measurement
uses the rebuilt checkout in `build/ngen-fhe16k54-block-control-rebuilt`; physical inference, resources,
and setup timing remain unverified until that vendor run completes. The
previous routed campaign is retained as the comparison baseline.

Corrected result: both rebuilt 16K/q54 directions passed all eight frames with
latency 69773 and initiation interval 73866, exactly matching the older baseline.
The generated block-ROM RTL, rather than source text alone, is the tested
artifact. The fresh block-only hardware candidate is `138ee4868aa5` (prefix)
in `build/ngen-fhe16k54-block-control-rebuilt`; simulation passed and synthesis
is queued under the common vendor lock.
