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
