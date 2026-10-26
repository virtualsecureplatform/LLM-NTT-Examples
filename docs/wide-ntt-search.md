# Wider internal NTT search

This bounded extension tests whether increasing internal NTT streaming width and
butterfly PE count improves the exact N=512 full32 × ternary polynomial product.
It keeps the external two-coefficient ready/valid product interface, Montgomery
reduction, radix R2, stage groups G1, baseline generator profile, and registered
product profile fixed. Wider internal lanes are not a change in coefficient
precision, polynomial size, or external interface bandwidth.

## Qualification grid

| Parameter | Values |
| --- | --- |
| Internal lanes | L2, L4, L8, L16 |
| PEs per engine | PE1, PE2, PE4, PE8 |
| Backend | NGen streamed |
| Workload | Exact full32 × ternary negacyclic multiplication modulo `2^32`, N=512 |
| Arithmetic / integration | Montgomery, R2, G1, registered product profile |
| Total selected configurations | 16 |

Four L2/L4 × PE1/PE2 points overlap the earlier registered pool. Twelve are new
width/PE combinations. The new campaign freshly evaluates all sixteen under its
recorded source/tool context. The study specification also enumerates the usual
arithmetic/FFT controls, but the runner explicitly selects only these sixteen NTT
points; unselected rows are not hardware attempts.

The candidate validators now admit internal widths up to L16 and PE counts up to
PE8 for NTT products. Defaults remain L2/L4 and PE1/PE2. Widths greater than the
transform length and PE counts greater than N/R are excluded. SGen width support
remains L2/L4. Backend-specific NGen lowering still determines concrete legality;
being enumerated does not establish functional or physical feasibility.

Each selected candidate follows the existing complete-product qualification:
independent integer-product checking over the full corpus, protocol/reset tests,
sustained interval measurement, swapped-operand checks, and pinned Yosys synthesis.
No reduction in qualification coverage is used for wider candidates. Failed,
unsupported, and timed-out cases remain visible. Stage-parallel architecture is
outside this sweep because it has a different interface/PE contract.

## Run, resume, and inspect

From the repository root, after preparing the existing pinned study toolchain:

```bash
scripts/run_wide_ntt_study.sh
# Resume an interrupted campaign:
scripts/run_wide_ntt_study.sh resume
```

The [specification](../studies/torus512-wide-ntt.json) defines the grid.
The [runner](../scripts/run_wide_ntt_study.sh) selects the NTT configurations and
then invokes the existing qualification and device-evaluation commands. Its
`wait` mode attaches to an already-running qualification campaign and queues
physical evaluation after every selected row has a terminal status; it does not
start a second qualification writer.

Local outputs:

| Path under `build/` | Contents |
| --- | --- |
| `polynomial-study-512-wide-ntt/summary.md` | Qualification and coarse-resource frontiers. |
| `polynomial-study-512-wide-ntt/all-points.csv` | Configuration fields, status, resources, latency, and interval. |
| `polynomial-study-512-wide-ntt/results.json` | Per-point measurements, failures, and artifact identities. Updated after each point finishes. |
| `polynomial-study-512-wide-ntt.log` | Current qualification point for the launched campaign. |
| `device-polynomial-512-wide-ntt/summary.md` | Physical-stage results, once finalists have been selected. |
| `device-polynomial-512-wide-ntt/points.csv` | Measured physical resources, timing, and feasibility. |
| `wide-ntt-pipeline.log` | Follow-up mapping/routing progress for the launched campaign. |

A pending row is not an achieved result. The controller's log and the candidate's
stage logs show current work before that row appears in the saved result file.
The initial launch and pipeline are background processes, so their output remains
available after the interactive session ends.

## Bounded physical follow-up

After qualification, consider passing L8/L16 designs only. Select the minimum
measured product interval, breaking ties by cells and point ID. Select a second,
distinct point with minimum generic cells, breaking ties by interval and ID.
These rules define a small shortlist; they do not predict the entire FPGA Pareto
frontier or ensure that the fastest coarse point meets timing.

The follow-up maps at most two candidates and routes at most two, with Vivado
2023.2, the U280 target, Default directives, registered harness v2, a 250 MHz
constraint, four tool threads, and 3,600-second stage timeouts. Failed mapping
or resource fit can prevent a route. No timing-repair loop is requested. The
physical report separates modeled rates from routed feasibility; only intact,
fully constrained, timing-qualified evidence is an achieved 250 MHz result.

## Export tables and graphs after qualification

Keep this campaign separate from the earlier three-workload grid snapshot:

```bash
python3 scripts/report_polynomial_study.py \
  --campaign build/polynomial-study-512-wide-ntt \
  --output-dir build/wide-ntt-report
build/polynomial-report-venv/bin/python - <<'PY'
from pathlib import Path
from scripts.plot_polynomial_study import load, resource_plot
folder = Path('build/wide-ntt-report')
resource_plot(load(folder / 'torus512-points.csv'), 512, folder)
PY
```

Read the lane/PE columns alongside the generic resource/throughput plot. The
vertical axis is products per 1,000 cycles (`1,000 / measured interval`), so
higher means faster. A throughput improvement at constant L identifies a PE
benefit; improvement at constant PE identifies a width benefit. More lanes alone can offer little improvement if
compute remains the bottleneck. The fixed external interface, frame banking,
pointwise operations, and CRT reconstruction can limit end-to-end gains. Routing
congestion and timing can reverse a coarse resource/cycle ranking.

See the [results presentation guide](dse-results-summary.md) for the prior grid,
measured 250 MHz frontier, and LLM experiment. This extension does not enlarge
the frozen 24-candidate LLM demonstration or its five-point replay dataset;
those require their own newly defined experiments and evidence.
