# HOGE square-switch composition

The switch adapter now recognizes namespaced NGen network definitions and preserves their complete module names. This allows the HOGE full-throughput backend's `HogeFTNGenSwitchTransposeNetwork_1` through `_5` to use SGen networks. Bare module names used by YATA remain supported. Incompatible packed widths are rejected before generation or RTL modification. Generation provenance lists every replaced module.

Validation in the isolated `hoge-sgen-namespaces` checkout used main NGen at `997122d` and a freshly assembled clean SGen checkout at `0f5a56d`. Candidate `6578a2a488ece5e93f48c083ab60157e18a79b3bd544ba8eff4f2375bbc77293` in `/tmp/llm-hoge-sgen/build/hoge-sgen-namespaced` passes the complete HOGE forward reference test: three test cases, 32 input cycles, 40 wait cycles, 32 output cycles, 104 transaction cycles. The generation record identifies all five replaced networks and 64-bit data. Synthesis is pending; this is functional evidence, not a timing claim.

Two composition regression tests pass, covering bare and prefixed names and rejecting malformed or heterogeneous packed widths without mutation. All 13 architecture-search tests also pass. The initial full Python suite in this isolated checkout encountered missing generated reference fixtures and missing sibling NGen. After supplying those existing local dependencies, the full suite runs 131 tests successfully (two skipped); log `/tmp/hoge-sgen-full-tests.out`.

The original failed attempt is retained in the main checkout at `build/ngen-sgen-hoge-forward-hardware`: its unprefixed-only adapter rejected HOGE before simulation. This branch stays separate while the live policy experiment retains its frozen framework sources.
