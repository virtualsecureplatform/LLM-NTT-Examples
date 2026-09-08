# HOGE square-switch composition

The switch adapter now recognizes namespaced NGen network definitions and preserves their complete module names. This allows the HOGE full-throughput backend's `HogeFTNGenSwitchTransposeNetwork_1` through `_5` to use SGen networks. Bare module names used by YATA remain supported. Incompatible packed widths are rejected before generation or RTL modification. Generation provenance lists every replaced module.

Validation in the isolated `hoge-sgen-namespaces` checkout used main NGen at `997122d` and a freshly assembled clean SGen checkout at `0f5a56d`. Candidate `6578a2a488ece5e93f48c083ab60157e18a79b3bd544ba8eff4f2375bbc77293` in `/tmp/llm-hoge-sgen/build/hoge-sgen-namespaced` passes the complete HOGE forward reference test: three test cases, 32 input cycles, 40 wait cycles, 32 output cycles, 104 transaction cycles. The generation record identifies all five replaced networks and 64-bit data. Synthesis is pending; this is functional evidence, not a timing claim.

Two composition regression tests pass, covering bare and prefixed names and rejecting malformed or heterogeneous packed widths without mutation. All 13 architecture-search tests also pass. The initial full Python suite in this isolated checkout encountered missing generated reference fixtures and missing sibling NGen. After supplying those existing local dependencies, the full suite runs 131 tests successfully (two skipped); log `/tmp/hoge-sgen-full-tests.out`.

The original failed attempt is retained in the main checkout at `build/ngen-sgen-hoge-forward-hardware`: its unprefixed-only adapter rejected HOGE before simulation. This branch stays separate while the live policy experiment retains its frozen framework sources.

## Overlapping-frame verification

The opt-in `hoge_streaming_ntt_overlap_test` target tests the full-throughput
contract separately from the unchanged original oracle. Both the original NGen
hardware candidate and the SGen-composed candidate pass 240 complete reference
frames: eight independently generated random frames for each combination of
input gap 0/1/3/31/32/33 cycles and reset-abort position 1/17/31/45/72 cycles.
The test checks every output word, uninterrupted output bursts, absence of extra
outputs, and output frame intervals equal to 32 plus the input gap. Saturated
frame interval is therefore verified as 32 cycles for these two RTL artifacts.
This does not qualify their hardware timing or imply board throughput.

Reproduce for either candidate by selecting its retained `NTTWrap.v`:

```sh
cmake -S . -B build/hoge-overlap -G Ninja \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DLLM_NTT_TEST_TARGET=hoge_streaming_ntt_overlap_test \
  -DHOGE_STREAMING_NTT_VERILOG=/absolute/path/to/NTTWrap.v
cmake --build build/hoge-overlap -j 8
build/hoge-overlap/hoge_streaming_ntt_overlap_test
```

Local successful logs are `/tmp/hoge-sgen-overlap-fixed.out` and
`/tmp/hoge-ngen-overlap.out`; both report `frames=240 saturated_interval=32`.
The first CMake invocation placed the new target after the unknown-target guard
and failed configuration. Moving the target before the guard fixes that build
setup; the retained failed log is `/tmp/hoge-sgen-overlap.out`.
