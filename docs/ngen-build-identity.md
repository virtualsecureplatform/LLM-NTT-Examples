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

The older full FHE matrix was already running with a frozen binary and verifier
snapshot when this guard was added. Its files were not changed. Direct library
entry points and the standalone matrix launcher still need the guard integrated
after that run ends; until then this enforcement applies to the ordinary search
CLI. Historical records retain their original provenance rather than receiving
retroactive build verification.
