# Matched policy study on realistic fields

This study tests whether the NGen architecture search can find feasible implementations on realistic FHE transform sizes. It compares enumeration, seeded random acquisition, measured-cost acquisition and LLM acquisition. The generator and policy implementations are frozen before measurements; every policy performs fresh RTL correctness and synthesis evaluations. No measurement is shared between policies or workloads.

Development covers forward and inverse FHE4096/32, FHE4096/60 and all four exact SEAL CKKS8192 primes from the validated suite (12 workloads). Held-out evaluation covers both directions of FHE16384/54 and FHE65536/54 (four workloads). These held-out cases already have functional validation; their new implementation outcomes are withheld from development. This phase measures NGen's generic engine, not an SGen comparison or an end-to-end FHE accelerator.

Each workload/policy trial receives three evaluations and its own two-hour wall budget, including acquisition and vendor queue time. There is one repetition (seed 2), for 64 trials and at most 192 fresh correctness/synthesis evaluations. Policy order rotates by workload to reduce systematic order bias. Failed acquisitions and unfinished evaluations remain visible and do not receive replacement budgets. A single repetition does not establish statistical superiority.

All policies use the unchanged realistic-v1 search spaces and U280 target at 4 ns, including the declared I/O delays and two output hold-buffer stages. Resource caps are 50,000 LUTs, 100,000 registers, 512 DSPs, 512 BRAM tiles and 64 URAMs. The service model permits 8 GB/s aggregate input/output traffic with 64-bit coefficients. Bandwidth-capped throughput is the minimum of measured engine throughput and this declared transport bound; the bound is not a measured board interface.

After all development synthesis trials, select the fastest bandwidth-capped feasible candidate and the lowest-LUT feasible candidate for each forward workload. Ties use canonical configuration and then policy name. A configuration selected twice is routed once. Missing resources, incorrect RTL, negative setup slack, target mismatch or unverified evidence make a candidate ineligible. Freeze the selection before routing. Each selected candidate receives up to three hours including queue time; route qualification additionally requires nonnegative hold slack. This produces at most 12 development routes. Inverse workloads receive synthesis evaluation only in this initial study.

After development routes finish, save the development summary and a held-out freeze marker. Run the same unchanged policies, caps and budgets on held-out workloads, then apply the same route rule (at most four routes). Policies receive observations only from their current trial. No post-development tuning occurs within this study.

The report records feasible discoveries, best bandwidth-capped throughput, candidate latency/resources, failures, completed evaluation counts, wall time and known/unknown queue time. It does not report frontier recall because the full reference space is not measured. Synthesis timing feasibility is distinct from routed closure. OOC fabric measurements do not establish board timing or superiority over AutoNTT, Proteus or OpenNTT.

## Execution and audit

Use detached, fixed-revision framework and NGen worktrees. Copy the assembled `ngen.bat` into the NGen worktree; preparation verifies its embedded source manifest. Source the native simulator tool environment before running. From the frozen framework checkout:

```bash
python3 scripts/run_realistic_study.py prepare --ngen-root /path/to/frozen-ngen --output-dir /path/to/new-study
python3 scripts/run_realistic_study.py run --output-dir /path/to/new-study
python3 scripts/run_realistic_study.py summarize --output-dir /path/to/new-study
```

`protocol.json` includes all 16 campaign paths/hashes, source revisions, assembly identity and executable input hashes. The runner checks these before each trial and route. Each live trial also seals its own inputs and saves acquisitions, raw LLM requests/responses, simulator evidence and vendor reports. Vendor jobs share the existing per-user Vivado lock. Other vendor processes may still compete for machine resources, so elapsed time is not described as uncontended.

The first startup (`realistic-policy-study-v1`) was aborted after six simulator crashes, before any hardware evaluations. GDB located SIGSEGV in Verilator 5.022's `VL_CVT_PACK_STR_NW`: generated absolute ROM filenames exceeded its default 256-byte conversion buffer. This was a simulator infrastructure failure, not an arithmetic mismatch. The replacement study restarts every policy with the same architecture settings and budgets. Its pinned wrapper passes `-CFLAGS -DVL_VALUE_STRING_MAX_WORDS=1024`, increasing that supported runtime buffer to 4096 bytes; a compiled regression exercises a filename longer than 256 bytes. The original failed results and protocol remain preserved.

`state.json` checkpoints scheduled work. `summary.json` can be refreshed during execution; `development-summary.json` and `final-summary.json` preserve phase results. `complete.json` means all scheduled attempts ended, not that every evaluation succeeded. An interrupted active attempt stops automatic resumption for inspection rather than silently overwriting evidence. Restarting the runner after a clean checkpoint skips completed work. Do not edit frozen inputs or remove checkpoints to manufacture a successful trial; corrections require a separately named study.

The worst-case allowance is 128 trial-hours plus 48 route-hours, excluding orchestration overhead. Actual completion depends on synthesis and routing runtimes. The runner is designed to continue detached across interactive sessions.
