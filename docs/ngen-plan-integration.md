# Prepared NGen integration

Pushed NGen branch `plan-integration`, revision `f4032e9`, combines registered
memory issue/effective metadata (`42de789`) and HOGE constant shifts (`d277ab4`).
It is built in `/tmp/ngen-plan-integration`. All 154 Scala tests pass and a fresh
assembly passes the source-to-executable identity guard. Main remains unchanged
while live policy inputs are frozen; the HOGE shift hardware ablation is pending.

Fresh generation in `build/plan-integration-rtl-identity-fixed/results.json`
verifies exact RTL SHA-256 equality and unchanged latency, frame interval,
pipeline depth, and input/output cycle declarations wherever present for:

- All six N=128 policy reference configurations.
- The timing-qualified registered-issue N=16384/q54 routed candidate.
- Forward and inverse HOGE constant-shift candidates.

The nine checks retain original report hashes, commands, generator build
identity, generated paths and RTL hashes. This proves artifact preservation
for those configurations. It does not supply a new hardware result or complete
the pending policy or HOGE measurements.

The first integration check failed exact byte equality for small generic cores:
two inactive optional declarations introduced blank lines. The integration
revision emits those lines only when registered issue is enabled. This preserves
small-core artifacts without changing the already-routed large-core artifact.
The failed check remains in `build/plan-integration-rtl-identity/incomplete.json`.

After the live experiment finishes, main can integrate this tested branch if the
remaining HOGE ablation supports retaining its optimization. Rebuild main and
verify its source manifest and artifact identities before finalizing the report.
