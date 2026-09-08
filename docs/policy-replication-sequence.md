# Scheduled policy replication

The current study is `build/live-policy128-three-seeds`; the clean repetition
will use `build/live-policy128-uncontended-three-seeds`. Both use four policies,
seeds 2/3/4, three fresh evaluations per trial and a 12-hour total budget.
The complete `build/policy128-reference-current` pool is used only for scoring.

The local orchestrator `build/policy-replication-sequence/run.py` waits for the
current process identity (PID plus kernel start time) to terminate. It then:

1. Verifies all 23 frozen executable input hashes.
2. Summarizes the completed current study, rejecting incomplete trial sets.
3. Checks that the shared Vivado lock is free, then releases it for the runner.
4. Starts the clean repetition in a fresh directory and records its PID.
5. Records its exit code, rechecks frozen inputs, and writes its summary.

No competing hardware campaigns will be launched during this sequence. The
initial lock check alone does not prove absence of later contention: inspect
recorded queue durations and failures before labeling the completed study
uncontended. A failed prerequisite stops the orchestrator without altering or
restarting the previous study. The original queue timeout remains a consumed
evaluation in the first summary.

The orchestrator's manifest records its own SHA-256, the original study manifest
hash, process start identity and replication parameters. It writes
`contended-summary.json`, `replication-start.json`, `replication-process.json`,
`replication-exit.json`, `replication.log`, and `uncontended-summary.json` as their
stages complete. Its supervisory log is `/tmp/policy-replication-sequence.out`.
These scheduled artifacts are not a claim that either study is complete.
