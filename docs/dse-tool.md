# Experiment CLI

For a combined view of the measured results and recommended presentation figures,
see the [DSE results summary](dse-results-summary.md).

Run a complete polynomial multiplication DSE replay from a fresh checkout using Python 3.9 or newer. The offline path uses the standard library: no FPGA tools, generator builds, submodules, plotting packages, or API key are required.

## First experiment

From the repository root:

```bash
python3 -m architecture_search.dse init experiment.json
python3 -m architecture_search.dse preflight experiment.json
python3 -m architecture_search.dse run experiment.json
python3 -m architecture_search.dse status experiment.json
python3 -m architecture_search.dse report experiment.json
```

The default experiment compares random and analytical policies on five bundled measured designs. Every policy receives the same passing seed and a budget of four additional candidates and two routing acquisitions. Replay reveals measurements only when the policy acquires their stage and charges the same logical budgets as live evaluation.

Open **`build/dse/experiment/report.html`** for the table, area/throughput chart, search-progress curves, and trial outcomes. It is a standalone HTML document with inline SVG and no external dependencies. The same directory contains `summary.md`, `comparison.svg`, `comparison.csv`, `points.csv`, and `comparison.json`. Reports are generated automatically after each policy completes; `report` regenerates them without evaluations or endpoint calls.

Run the same command again to resume:

```bash
python3 -m architecture_search.dse run experiment.json
```

Completed policies are verified and reused. A completed experiment can be reopened without credentials or a reachable LLM endpoint. `init` refuses to overwrite an existing configuration.

## Add the LLM policy

```bash
python3 -m architecture_search.dse init llm-experiment.json --with-llm
read -rsp 'LLM endpoint key: ' LLM_DSE_API_KEY
export LLM_DSE_API_KEY
python3 -m architecture_search.dse preflight llm-experiment.json
python3 -m architecture_search.dse run llm-experiment.json
```

This adds LLM selection to the same random/analytical comparison. The default endpoint is `http://10.0.60.37:8080/v1`, model `qwen3.8-flash-next-unsloth-ud-q4_k_xl`. Change the `llm.base_url` and `llm.model` fields in the generated JSON for another compatible endpoint. Preflight authenticates `/models` and checks the requested model before starting trials. Redirects are refused. Credentials belong in `LLM_DSE_API_KEY`; the configuration accepts no API-key field, and hardware workers receive no key.

## Configure and inspect

The generated JSON is the experiment definition. It contains the workload and legal search axes under `study`, the FPGA/context/bandwidth/resource settings under `target`, the policies and seed, budgets, endpoint, replay dataset, live paths, and output directory. The current workload remains exact N=512 full32 × ternary negacyclic multiplication modulo 2^32, with the Default 250 MHz registered harness v2.

- `policies`: a unique nonempty subset of `llm`, `random`, and `analytical`.
- `budgets`: candidate attempts, routing attempts, stage timeout in seconds, and tool threads. Routes must not exceed half the candidate budget. The bundled replay has four non-seed candidates, so its candidate budget is at most four.
- `output_dir`: relative to the configuration file, or absolute. The default is `build/dse/<configuration-stem>` relative to that file.
- `replay_dataset`: `bundled:torus512`, or a JSON path with a companion `.sha256` file. Relative custom paths resolve against the configuration directory.
- `live.reference` and `live.cache`: support the `repo:` prefix for paths relative to the repository. Other relative paths resolve against the configuration directory. `live.vivado` accepts an executable path or a name on `PATH`.

Configuration and interface-source fingerprints are frozen when a run starts. Changing experiment settings requires a different `output_dir`. Status shows the saved experiment and warns if the current configuration differs. Replay configurations and outputs can be moved together to another checkout without retaining their original absolute paths.

```bash
python3 -m architecture_search.dse status experiment.json --json
python3 -m architecture_search.dse preflight experiment.json --json
```

Status shows each policy, current design and stage, elapsed stage time, remaining budgets, feasible designs, best modeled rate, and explicit failure reasons. It also identifies an active LLM inference request. Status is read-only and works while the run holds its writer lock. A simultaneous second `run` or `report` is rejected; the last generated report remains available to view during execution.

## Live evaluation

```bash
python3 -m architecture_search.dse init live-experiment.json --mode live --with-llm
python3 -m architecture_search.dse preflight live-experiment.json
python3 -m architecture_search.dse run live-experiment.json
```

Preflight checks Apptainer, the NGen assembly/source identity, pinned image, Yosys, container Java/Verilator, Vivado identity, reusable seed qualification and routed evidence, and the endpoint when needed. Missing prerequisites produce actionable errors before any trials. See the [device setup and seed campaign guide](device-polynomial-search.md) for the live prerequisites. The default reference is `repo:build/device-pareto250-512`; set `live.reference` to the completed matching-context campaign in your workspace.

The live path uses the existing qualification, mapping, routing, cache, and restart machinery. Failed timing is reported as, for example, `setup timing failed (-5.374 ns slack)` rather than just native tool success. Fully constrained timing, zero failing endpoints, resources, clock-route proofs, and intact native evidence still decide qualification. Reports validate acquired evidence without launching new synthesis or routing.

## Replay evidence and limits

`data/dse/torus512-replay.json` contains five measurements exported from the [published 250 MHz frontier](results/pareto250-512.md). The export verified the original qualification, P&R, endpoint counts, and clock proofs; the bundle retains provenance hashes and compact metrics. Loading checks its SHA-256, legal configurations, workload/target identity, finite metrics, and consistent reported signoff. Resuming/reporting also checks acquired records against the bundle.

**Portable replay reuses published measurements; it does not perform local RTL or checkpoint signoff.** Its reports label that distinction. It is a closed integration fixture, not a complete 24-point oracle or evidence of reduced search effort. Throughput remains modeled from qualified cycles and bandwidth assumptions, not a board measurement. See the [prototype guide](llm-polynomial-search.md) for the original live comparison and interpretation.

Maintainers with the original native artifacts can reproduce the bundle with:

```bash
python3 scripts/export_dse_replay.py
```

The original script entrypoints and historical result snapshots remain available.
