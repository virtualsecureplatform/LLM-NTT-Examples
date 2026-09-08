# FHE matrix validation

All 18 independent registered-stream oracle checks pass with compact NGen
address logic and exact control-ROM externalization. The generator snapshot
is from `compact-stream-io` at `c531b18`; these generic changes are now on main.
Each case uses PE=2, radix=2, Montgomery reduction, one stage group, four
external lanes, and the exact field/root/twist saved in its campaign.

| N | Field bits | Direction | Latency cycles | Frame interval cycles |
| ---: | ---: | --- | ---: | ---: |
| 131072 | 32 | forward | 655528 | 688293 |
| 131072 | 32 | inverse | 655528 | 688293 |
| 131072 | 54 | forward | 655528 | 688293 |
| 131072 | 54 | inverse | 655528 | 688293 |
| 131072 | 64 | forward | 655528 | 688293 |
| 131072 | 64 | inverse | 655528 | 688293 |
| 16384 | 32 | forward | 69773 | 73866 |
| 16384 | 32 | inverse | 69773 | 73866 |
| 16384 | 54 | forward | 69773 | 73866 |
| 16384 | 54 | inverse | 69773 | 73866 |
| 16384 | 64 | forward | 69773 | 73866 |
| 16384 | 64 | inverse | 69773 | 73866 |
| 65536 | 32 | forward | 311455 | 327836 |
| 65536 | 32 | inverse | 311455 | 327836 |
| 65536 | 54 | forward | 311455 | 327836 |
| 65536 | 54 | inverse | 311455 | 327836 |
| 65536 | 64 | forward | 311455 | 327836 |
| 65536 | 64 | inverse | 311455 | 327836 |

Every case runs eight arithmetic vectors, input gaps, saturated traffic, output
backpressure, output stability, and reset recovery. A pass requires the final
PASS marker after the reset suite, not merely the eight main-frame metrics.
These are simulation results; they do not establish FPGA fit or routed timing.

The artifact is `build/fhe-compact-verilator-matrix`; its root manifest records
the generator binary and helper identities. Per-case records preserve the
actual command, registered-boundary adapter, original hardware RTL hash,
simulation-only ROM files, test vectors, and testbench hashes.

The normal search runner now selects Verilator for generic N >= 16384 and
Icarus for smaller transforms. Override this explicitly if needed:

```json
"evaluation": {"simulator": "verilator", "timeout_seconds": 1200}
```

Allowed simulators are `auto`, `iverilog`, and `verilator`. Verilator uses a
private copy with ROM initialization externalized; synthesis continues to use
the original self-contained generated RTL. Both simulators run the same
independent oracle and protocol suite. Timeout and compilation failure remain
failed results. A small integration test checks equal metrics from both tools
and verifies that hardware RTL remains unchanged.

The original 128K Icarus timeout and signal-9 Verilator attempts are retained.
They motivated compact emission and are not retroactively relabeled as passes.

The ordinary search command also passes N=128K/q64 inverse from integrated
NGen main in `build/fhe-main-auto-n131072-q64-inverse`. It automatically selects
Verilator, passes the complete oracle, and reports latency 655528 and frame
interval 688293 cycles with unchanged hardware RTL. Thus the large check is
available through the normal campaign entry point, not just the matrix helper.

All 103 Python tests pass after regenerating their required reference fixtures
with `sbt 'runMain hoge.HogeTops'` in `variants/hoge/chisel` and
`sbt 'runMain YataRainttTop'` in `variants/yata-raintt/chisel`. The first broader
suite run recorded nine missing-reference-file errors; no tests were skipped
or weakened to obtain the passing result. Generated fixtures remain build
artifacts. NGen's integrated Scala suite separately passes all 148 tests.
