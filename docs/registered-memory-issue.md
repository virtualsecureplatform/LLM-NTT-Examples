# Registered memory issue for large PE schedules

NGen branch `pipeline-control-rom`, commit `c6445a6`, inserts registers after
control-ROM bank/address decoding for radix-2 schedules with at least 1024
operation bundles. This targets the failed 16K routed path from a control-ROM
output to a coefficient-memory enable. Read enables/addresses are registered
per physical buffer/bank; control tags receive the same extra delay before
loading arithmetic operands. The pipeline keeps one issue per cycle within a
stage and drains completely at stage boundaries.

The extra read-issue stage adds one cycle per drained stage. Generator timing
estimates account for it. Small schedules and fused-radix schedules retain their
previous issue path. The implementation is isolated in
`/tmp/ngen-control-pipeline` so the ongoing policy experiment continues to use
its fixed main-branch executable. It has not yet been integrated into main.

A fresh assembly passes all 152 Scala tests, including a large-schedule RTL
compile and timing-accounting regression. Both 16K/q54 directions pass the
unchanged full eight-frame oracle in
`build/registered-issue-fixed16k54-{forward,inverse}`:

| Metric | Prior wide-product pipeline | Registered issue |
| --- | ---: | ---: |
| First-output latency | 69803 | 69818 |
| Initiation interval | 73896 | 73911 |

The +15 cycles match one extra cycle over 15 stage drains. Reset, input gaps,
saturation, output stalls and output stability remain checked by the same
oracle. The initial attempts in `build/registered-issue16k54-*` failed RTL
parsing; missing generated-block separation and declaration ordering were
fixed before these successful runs. The compile regression retains that fault
coverage.

The full 18-case matrix is running in `build/fhe-registered-issue-matrix`.
`campaigns/fhe16k54-registered-issue-route.json`, with
`--ngen-root /tmp/ngen-control-pipeline`, queues a fresh matched route in
`build/ngen-fhe16k54-registered-issue-route`. No timing or resource improvement
is claimed until implementation finishes. The previous -0.459 ns route remains
the comparison baseline.

Routed measurement completes and passes: 8423 LUT, 3667 FF, 66 DSP, 376 BRAM,
setup WNS +0.124 ns and hold +0.011 ns under the same 4 ns fabric contract.
`build/comparison16k54-registered-issue-routed` compares the verified artifact
with the banked OpenNTT adapter; both enter its routed frontier. Relative to
OpenNTT, NGen has 33.1% higher route-qualified RTL-derived transform throughput
and 25.9% lower latency, with fewer FF/DSP and higher LUT/BRAM use. This is not a
board or universal-generator claim. Main-branch integration remains pending.

The full registered-issue FHE matrix completes all 18 cases successfully. A
follow-up metadata-only update on the experiment branch reports
`registered_memory_issue_groups` and `block_control_rom_groups`, calculated from
the actual partition schedules rather than the full-transform schedule. A
1024-point, three-partition test has bundle counts 768/768/1024 and correctly
reports one eligible group. Runtime-writable control does not claim block ROM.

All 153 Scala tests pass. `build/issue-metadata-validation/results.json` records
fresh generation whose 16K RTL SHA-256 exactly equals the routed artifact and
whose latency/interval declarations are unchanged. The mixed-partition sidecar
also agrees with the emitted block-ROM declarations. This metadata update does
not introduce a new unmeasured hardware revision; the proven byte equality is
retained explicitly. Main integration still waits for the fixed-input policy
experiment.
