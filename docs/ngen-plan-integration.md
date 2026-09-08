# Prepared NGen integration

Pushed NGen branch `plan-integration`, revision `f4032e9`, combines registered
memory issue/effective metadata (`42de789`) and HOGE constant shifts (`d277ab4`).
It is built in `/tmp/ngen-plan-integration`. All 154 Scala tests pass and a fresh
assembly passes the source-to-executable identity guard. Main remains unchanged
while live policy inputs are frozen. The completed HOGE forward shift ablation
supports retaining the specialization as a DSP/LUT tradeoff, with worse setup
slack and no timing-qualified throughput advantage.

Fresh generation in `build/plan-integration-rtl-identity-fixed/results.json`
verifies exact RTL SHA-256 equality and unchanged latency, frame interval,
pipeline depth, and input/output cycle declarations wherever present for:

- All six N=128 policy reference configurations.
- The timing-qualified registered-issue N=16384/q54 routed candidate.
- Forward and inverse HOGE constant-shift candidates.

The nine checks retain original report hashes, commands, generator build
identity, generated paths and RTL hashes. This proves artifact preservation
for those configurations. It does not supply a new hardware result or complete
the pending policy measurements.

The first integration check failed exact byte equality for small generic cores:
two inactive optional declarations introduced blank lines. The integration
revision emits those lines only when registered issue is enabled. This preserves
small-core artifacts without changing the already-routed large-core artifact.
The failed check remains in `build/plan-integration-rtl-identity/incomplete.json`.

After both live policy studies finish, main can integrate this tested branch.
Rebuild main and
verify its source manifest and artifact identities before finalizing the report.

The combined framework/SGen checks also pass with this NGen integration:
forward and inverse HOGE retain 104/73 transaction cycles, and the forward
frame-overlap check passes 240 frames at interval 32. Framework branch
`hoge-sgen-namespaces` at `4f0cab9` contains the campaigns and test, and all
131 Python tests pass without skips.

Completed combined HOGE evidence is preserved outside the temporary worktree in
`build/integration-evidence-archive/combined-hoge-evidence.tar.gz` (36,139,441 bytes),
SHA-256 `79fbcef6f5ea209fd24bfd07c9699782f6d711cc3feb060538bda353d2e13ab5`.
Its `manifest.json` lists the original path, archive path and SHA-256 for all
214 files; every archived payload was read back and verified. The archive
includes both completed search runs, the overlap run and its test/CMake sources.
It excludes still-running hardware jobs. Recorded JSON/build paths remain the
original absolute paths; this is an exact evidence archive, not a relocated
measurement or a new timing result.

The integration preservation check now covers the entire 18-case FHE matrix
(N=16K/64K/128K, fields of 32/54/64 bits, both directions). Every regenerated
RTL hash and timing declaration matches its originally validated artifact.
Before comparison, the check revalidates the original candidate and campaign
manifest hashes, verification-result hash, and all retained verification-input
hashes. Results and the exact check script are retained in
`build/plan-integration-fhe-identity/{results.json,check.py}`. This establishes
preservation of the complete validated matrix, not a new simulation or timing
measurement. The original 18 full-oracle passes remain the functional evidence.

The framework branch `plan-integration` at `1b4e6e7` combines the namespaced
SGen composition, HOGE overlap test/campaigns, and queue-timeout elapsed-duration
fix with main at `5f7c3a9`, including the completed HOGE comparisons and explicit
external-report root support. All 134 Python tests pass with native tools enabled
(`/tmp/llm-plan-integration-final-tests.out`). This branch is pushed; main remains
frozen for the running policy study.
