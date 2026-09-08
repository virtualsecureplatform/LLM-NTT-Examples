# Hardware evidence integrity

New vendor measurements retain SHA-256 manifests of input RTL, extra sources,
explicit dependencies (including external baseline ROMs and oracle artifacts),
include-directory contents, and the snapshotted implementation drivers. Inputs
are checked again after the vendor process; drift makes the measurement fail.
Metrics JSON, implementation reports, checkpoints, generated Tcl, and the process
log are hashed when reported by the driver. The measured target, timing flags,
and original metrics are retained alongside those manifests.

Pareto comparisons reject new evidence whose files are missing or changed, or
whose measured fields differ. Policy replay also rejects such pools. Additional
derived metrics may be added without changing the original measured fields.
`evidence_integrity` returns `verified`, `invalid`, or `legacy-unverified`;
older records remain usable but do not gain retroactive verification. Manifests
use absolute paths, so relocating an evidence bundle requires preserving those
paths or a separate explicit import workflow. This detects accidental drift;
it is not a signature or protection against deliberate manifest rewriting.

Validation: 113 Python tests pass, including RTL/ROM mutation during measurement,
include-file addition/removal, edited metrics/report artifacts, and preservation
of legacy evidence. Existing vendor report and policy replay regressions pass.
