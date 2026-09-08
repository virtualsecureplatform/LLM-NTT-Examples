# NGen executable freshness

NGen assembly now embeds `META-INF/ngen/source-inputs.sha256` inside `ngen.bat`.
It hashes `build.sbt`, main Scala/resources, and project Scala/sbt/properties
inputs, excluding generated project output. Test-only edits do not require a
new executable. The manifest is deterministic and records additions/deletions
as well as changed file contents when compared with the current checkout.

`python3 scripts/check_ngen_build.py --ngen-root ../NGen` verifies those inputs
against the assembled executable. The `search_architectures.py` launcher checks
this before run/resume. Planning and historical reporting do not execute the
generator and remain available. Missing manifests, changed inputs and invalid
archives fail before campaign creation, with an instruction to run `sbt
assembly`. Legacy revisions without the manifest must be reproduced with their
recorded original tooling; they are not silently declared build-verified.

This binds an executable to declared source/build inputs, not to every detail
of the host or dependency resolver. Existing tool-version, source-identity and
binary hashes remain necessary. It is an accidental-staleness check, not a
cryptographic signature of a trusted compiler.

Validation covers modified/added/deleted source, build changes, test-only edits,
excluded generated files, legacy binaries, and launcher rejection before output
creation. A fresh guarded N=256/q54 campaign passes the full oracle in
`build/build-verified-search256-q54`. The embedded manifest covers 68 inputs.

Enforcement also applies to direct search calls, generator adapters, and the
standalone matrix launcher. Generation checks the build again after execution
and records its verified identity, catching source/binary changes during the
call. Campaign and matrix manifests retain that identity. A fresh standalone
matrix check passes in `build/build-verified-matrix256-fixed`.

The first isolated matrix smoke test exposed infinite provenance recursion on
an uninitialized submodule: Git inherited the parent repository and repeated
its file list. Provenance now records that gitlink as uninitialized. Its failure
is preserved in `build/build-verified-matrix256`; the corrected test passes.
Historical measurements receive no retroactive build verification.
