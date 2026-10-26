# LLM-guided polynomial multiplication search

For a combined view of the measured results and recommended presentation figures,
see the [DSE results summary](dse-results-summary.md).

For new experiments, start with the [unified experiment CLI](dse-tool.md). It
provides configuration, preflight, status, automatic reports, and a bundled
portable replay that works without the local build/evidence directories required
by the original commands below.

This prototype searches exact N=512 full32 × ternary negacyclic polynomial products modulo 2^32. It selects configurations from existing NGen generators and evaluates their measured feedback. The primary objectives are lower routed LUT use and higher modeled products/s, with exact correctness, U280 resource limits, and routed 250 MHz timing as requirements.

The 24 legal configurations vary product profile (`pipelined`, `registered`), lanes (2, 4), PEs (1, 2), and modular reduction (Barrett, Montgomery, Shoup). The backend is streamed radix 2 with stage grouping 1 and baseline arithmetic profile. Legality permits evaluation; functional qualification still decides whether each implementation passes. FFT and generated RTL edits are outside this first experiment.

## Endpoint and credentials

The default endpoint is `http://10.0.60.37:8080/v1`, model `qwen3.8-flash-next-unsloth-ud-q4_k_xl`. It uses JSON chat completions with temperature 0. Endpoint and model overrides are `LLM_DSE_BASE_URL`, `LLM_DSE_MODEL`, `--base-url`, and `--model`.

Supply the endpoint credential through the environment:

```bash
read -rsp 'LLM endpoint key: ' LLM_DSE_API_KEY
export LLM_DSE_API_KEY
```

The client retains the key in memory and redacts it from saved responses. Hardware workers receive no key. There is no API-key command-line argument or tracked credential file. Each selection allows three HTTP requests in total, including invalid responses, network failures, and resumed attempts. The accepted proposal is saved before hardware execution. Saved transcripts contain request bodies, redacted responses, timing, and token usage; authorization headers are excluded. Temperature 0 does not guarantee identical future model responses: transcripts provide the actual experiment record.

## Run the demonstration

Inspect the catalog without invoking hardware or the endpoint:

```bash
python3 scripts/llm_polynomial_study.py --mode live --dry-run
```

Run the closed replay fixture first:

```bash
python3 -u scripts/llm_polynomial_study.py \
  --mode replay --policy compare --output-dir build/llm-dse-replay
```

Replay uses the five completed matching-context designs in `build/device-pareto250-512`. It checks feedback, selection, promotion, and accounting without additional Vivado executions. Its measured oracle stays inside the evaluator; policies see configurations and disclosed observations only. This is an integration fixture, not a test of search reduction over the 24-point grid.

Run the bounded live comparison:

```bash
python3 -u scripts/llm_polynomial_study.py \
  --mode live --policy compare --output-dir build/llm-dse-live
```

The default comparison runs LLM, seeded random, and the existing analytical acquisition heuristic, in that order, using seed 1. The heuristic alternates its arithmetic/storage proxy and interval estimate, with its existing seeded exploration step. Configuration-derived estimates are available without measuring hidden candidates.

Each policy receives the same pipelined Montgomery lanes-2 PE-1 passing seed as disclosed prior evidence. Each may attempt four additional candidates, up to four mappings, and two routings. A failed qualification consumes its candidate attempt and stops that candidate before mapping. The common seed is excluded from these budgets. The comparison requires at most 12 new qualifications, 12 mappings, and six routings before shared-cache reuse; it does not pre-evaluate all 24 configurations.

After attempts 2 and 4, the common scheduler promotes a mapped, resource-fitting design. The first promotion prefers highest modeled throughput and then lowest mapped LUTs; the second reverses those priorities. IDs break remaining ties. Unused promotions wait for an eligible design. Negative mapped slack influences neither eligibility nor achieved feasibility: routed signoff decides timing. The LLM receives routing feedback before its next candidate selection.

Live qualification uses the pinned Apptainer image, full existing product scoreboard, protocol/reset and swapped-input checks, cycle measurement, and Yosys counts. Vivado 2023.2 runs serially with four threads by default, using the unchanged registered harness v2 and Default directive. Each qualification, mapping, and routing stage has a 3,600-second deadline. No timing-repair directives run in this experiment.

Use `--max-candidates`, `--route-budget`, `--seed`, `--timeout`, or `--threads` for a new experiment. Routing budget must not exceed half the candidate budget. `--policy llm`, `random`, or `analytical` runs one policy. Changing experiment settings requires a new output directory.

## Status, restart, and cache

```bash
python3 scripts/llm_polynomial_study.py --status --output-dir build/llm-dse-live
python3 -u scripts/llm_polynomial_study.py \
  --mode live --policy compare --output-dir build/llm-dse-live --resume
```

Runs save the selected proposal, active stage, attempts, measurements, and frontier progress. A resume adopts sealed stage evidence without repeating completed evaluations. An unsealed interrupted attempt is charged once and recorded as failed. A still-running orphan worker must finish before recovery. Run and cache locks prevent overlapping writers.

The shared cache is under `build/llm-dse-cache` by default. Its context includes hardware source hashes, generator assembly, image, corpus, RTL, harness, target, Vivado identity, evaluator, and execution settings. Imported qualification additionally checks current composition, the archived scoreboard implementations, and all required functional results. Mapped and routed evidence require the exact current target and tool identity; historical standalone and v1 harness studies are separate contexts. A timing-feasible result requires intact evidence, resource fit, fully constrained timing, nonnegative slacks, explicitly zero failing endpoints, and a separately verified routed clock.

Cache hits reveal only the stage the policy acquired and consume identical logical budgets to fresh executions. Newly executed stages and physical time are counted separately. Physical savings depend on policy order and prior cache contents; logical candidate/routing counts are the comparison budget. Historical imported hardware durations reflect available recorded process durations, while imported qualification duration is unavailable and represented as zero.

## Results and interpretation

Each policy has `manifest.json`, `results.json`, and its own redacted LLM transcripts. The comparison directory contains:

- `summary.md`, `comparison.csv`, and `comparison.json`: policy outcomes, stage budgets, physical executions, cache hits, failures, hardware durations, LLM latency, and token usage.
- `points.csv`: achieved resource/throughput points, primary two-objective membership, and the existing eight-objective frontier membership.
- `comparison.svg` and `comparison.png`: routed LUT/throughput tradeoffs and hypervolume progress against candidate and routing attempts.

Plots use the packages in `scripts/polynomial-report-requirements.txt`. When those packages are absent from the controller environment, generate them afterward with the reporting environment:

```bash
build/polynomial-report-venv/bin/python scripts/llm_polynomial_study.py \
  --plot-only --output-dir build/llm-dse-live
```

Hypervolume uses a fixed reference of the target LUT limit and zero throughput, normalized by LUT limit × seed throughput. The secondary full frontier minimizes error, LUT, FF, DSP, BRAM36, URAM, and latency, and maximizes modeled throughput. Every point in these frontiers must pass routed 250 MHz qualification.

Products/s are modeled from qualified cycles at 250 MHz and the fixed bandwidth assumption; they are not board measurements. This initial single-seed comparison is exploratory. It establishes a functioning adaptive search loop and produces inspectable evidence. A full-grid reference, repeated independent trials, and a demonstrated LLM search advantage are subsequent experiments.

Publish a compact snapshot after a comparison completes:

```bash
build/polynomial-report-venv/bin/python scripts/report_llm_polynomial_study.py \
  --campaign build/llm-dse-live --prefix llm-dse-live-512
```

The publisher verifies completed run hashes, controller/evaluator sources, transcripts, functional evidence, routed evidence, clock proofs, and recomputed frontier progress before copying tables and plots to `docs/results/`.

The completed [five-design replay comparison](results/llm-dse-replay-512.md) includes the real-endpoint LLM trace and matched random/analytical comparisons. It is a closed-fixture integration result.

The completed [bounded live comparison](results/llm-dse-live-512.md) acquired nine distinct designs, including the common seed. Five new qualifications, seven new mappings, and five new routings supplied the shared evidence for three four-candidate/two-route runs. LLM and random both reached 141,483 modeled products/s at routed 250 MHz; the analytical baseline retained the 72,886-products/s seed. This single-seed result does not establish an LLM advantage over random search.
