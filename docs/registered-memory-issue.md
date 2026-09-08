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
