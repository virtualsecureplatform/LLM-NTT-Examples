# Hardware budget outcomes

The first NGen HOGE inverse stage-parallel synthesis ends with exit 124 after
5379.81 seconds (`build/ngen-hoge-inverse-hardware`, candidate `a410fc119fbc`).
It passes the arithmetic oracle at 69 transaction cycles, but produces no final
utilization or timing report before its execution budget expires. It is
unmeasured hardware, not evidence of timing closure or a measured resource-fit
failure. The synthesis log retains its intermediate optimization reports.

The first composed HOGE forward measurement also expires:
`/tmp/llm-hoge-sgen/build/hoge-sgen-namespaced`, candidate `6578a2a488ec`, spends
5340.26 seconds queued and has only 59 seconds available for vendor execution.
The original process and workers are confirmed stopped. A fresh attempt is
running in `build/hoge-sgen-forward-hardware-retry`, preserving the original
failed run and the same pre-shift NGen/SGen composition. This is a fresh
measurement budget after the long-running inverse job ended.

The live policy experiment retains a queue timeout for random/seed 2/step 1.
The candidate consumed an evaluation budget but obtained no hardware result.
The original runner omitted queue duration on that return path. The standalone
summary now leaves that duration null rather than treating it as zero, exposes
known queue time separately, and classifies queue, execution and timing failures.
Policy aggregates also identify repetitions with queue or execution timeouts.
Such failures confound frontier recovery as well as wall-time comparisons;
they are not evidence about an acquisition policy's architecture choices.
All 23 frozen policy inputs remain unchanged. The runner's missing queue-duration
field itself remains to be corrected after this frozen experiment ends.

All 131 Python tests pass, including separate regressions for unknown queue
latency and execution versus timing failure; the seven summary tests also pass
after adding aggregate timeout counts. The active repetitions continue with
the original inputs and their failures retained. Final policy conclusions must
explicitly report this contention rather than silently replacing observations.

A separate inverse full-throughput candidate is queued with
`campaigns/hoge-inverse-full-throughput-hardware.json` and NGen integration
revision `f4032e9`, under `build/hoge-inverse-full-throughput-hardware`. This
architecture already passes the independent inverse oracle at 73 transaction
cycles and uses the same fixed task boundary as the extracted reference. Its
hardware metrics remain pending. It is an additional architecture choice;
the original 69-cycle stage-parallel timeout remains part of the comparison.

The extracted inverse reference completes synthesis with 140242 LUT, 239475 FF,
512 DSP and zero BRAM/URAM. Setup slack is +1.518 ns; estimated hold slack is
−0.075 ns. It passes the synthesis setup gate but has no routed-closure claim.
The comparison snapshot explicitly describes this stage-specific gate.

The future runner fix is pushed on branch `report-queue-timeout` at `bb8fb68`.
Its held-lock regression verifies elapsed queue duration and that no vendor
execution occurs on queue timeout; all three hardware-report and seven summary
tests pass. Main integration awaits the frozen policy run. A subsequent policy
replication without competing hardware campaigns is required to separate policy
choice quality from the current run's queue-induced failures; original results
will remain retained.

The full-throughput inverse measurement completes in 370.57 vendor seconds:
136166 LUT, 34058 FF, 512 DSP, zero BRAM/URAM, WNS −9.844 ns and hold
−0.029 ns. Its smaller simulated 73-cycle transaction is not a qualified
250 MHz result. `build/hoge-inverse-architecture-comparison` now retains the
extracted reference, the stage-parallel timeout and this measured setup failure.
`campaigns/hoge-inverse-comparison.json` spells out the actual clock port so
strict target matching succeeds without relaxing the comparison gate.

The first forward constant-shift measurement ends with `Vivado queue timeout`
and no vendor execution (`build/hoge-forward-shifts-hardware`). A fresh attempt
is running in `build/hoge-forward-shifts-hardware-retry` with the same assembled
NGen shift revision. The stopped queue-limited attempt remains retained.
