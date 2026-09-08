# Extracted preset baseline comparisons

`evaluate_preset_baseline.py` copies a reference top into an isolated result
directory and runs the unchanged task evaluator. It records source identity,
task/RTL hashes, original extra-source hashes, and the copied RTL hash. Lint-only
success and input changes cannot become functional evidence. Optional hardware
measurement uses the shared vendor lock and normal timing gates. A matching
NGen report can be imported only under the same task and target, with unchanged
RTL. Legacy transaction counts remain distinct from sustained throughput.

The checked-in HOGE baseline JSON was lint-only, and generated Chisel RTL was
absent. Fresh HOGE RTL was generated from an isolated copy of
`variants/hoge/chisel` using `runMain hoge.streaming.HogeStreamingTops`, with
source inputs and the command recorded in
`build/hoge-extracted-generation/source-manifest.json`. Both freshly generated
HOGE directions now pass the current arithmetic tests.

| Task | Extracted reference transaction | NGen comparison transaction | Evidence directory under `build/` |
| --- | ---: | ---: | --- |
| Kyber PE1 | 1414 | 1663 (main microcoded backend) | kyber-extracted-comparison |
| YATA 8x8 | 17 | 96 (microcoded + SGen stride RAM) | yata-extracted-comparison |
| HOGE forward | 170 | 104 (full-throughput switch), 1986 (microcoded indexed), 2017 (microcoded switch) | hoge-forward-extracted-comparison |
| HOGE inverse | 129 | 69 (stage-parallel indexed) | hoge-inverse-extracted-comparison |

All counts include the harness's input, maximum wait, and output bursts. These
are functional/cycle comparisons, not achieved-clock or area-normalized wins.
In particular the very short YATA reference transaction does not establish that
its combinational design meets 250 MHz. Original failed NGen elaboration attempts
remain in their original reports rather than being silently replaced.

Example:

```sh
python3 scripts/evaluate_preset_baseline.py --campaign campaigns/kyber.json --ngen-report build/kyber-explicit-validation/report.json --output-dir build/kyber-extracted-comparison
```

## Isolated Kyber normalization improvement

The cycle comparison identified a separate 256-operation inverse normalization
pass in NGen. Commit `a181673`, on the `improve-kyber-normalization` branch,
distributes division by two across all seven inverse layers. The sum output
uses canonical modular halving, and inverse-two is folded into the difference
output's twiddle constant. Seven linear layers thus accumulate inverse-128
normalization without the final pass.

`build/kyber-normalization-validation` passes the unchanged PE1 vectors for
forward/inverse and both banks. Its worst transaction is 1407 cycles, versus
1663 before the change and 1414 for the extracted reference. The generated
halving function also passes all 3329 canonical residues against multiplication
by inverse-two (`scripts/test_kyber_half.sh` in that branch).

The change is isolated in `/tmp/ngen-kyber-normalization` to preserve executable
inputs of active live trials. It is not yet merged into main and still needs
matched implementation measurements; a seven-cycle transaction advantage is
not a timing-closed hardware speedup.

## Integrated Kyber hardware check

NGen main now includes inverse normalization distributed across the seven
butterfly layers. The unchanged combined forward/inverse preset test passes
with 1407 transaction cycles. Synthesis under the original 4 ns Kyber target
in `build/kyber-normalization-main-hardware` uses 23165 LUTs, 9456 FFs, six
DSPs, and three BRAM tiles, but fails timing: WNS -6.720 ns and WHS -0.075 ns.
The critical path is control-ROM output `pc_reg_rep__4/CLKARDCLK` through work
selection and modular arithmetic to `work_reg[160][3]/D`, with 10.654 ns data
delay and 39 logic levels. Reducing transaction cycles did not establish a
4 ns hardware implementation. Matched extracted-reference synthesis is running;
the failing NGen point remains outside the hardware frontier.

The extracted Kyber reference completed synthesis: 777 LUTs, 353 FFs, one DSP,
2.5 BRAM tiles and WNS +1.307 ns (`build/kyber-extracted-hardware-comparison`).
Its synthesis hold estimate is -0.042 ns; only routed checks enforce full hold
closure, so this is not a routed result. Its 1414 transaction cycles and much
smaller area establish that NGen's work-array architecture still needs improvement.

An isolated `ngen-kyber-pipeline` worktree now separates instruction fetch, work
read, inverse preprocessing, product, Montgomery correction, multiply-add,
reduction, and retirement. Forward and inverse share one datapath. Generation
checks every scheduled address dependency against the pipeline distance. The
full unchanged preset oracle passes at 1414 transaction cycles, including both
banks/directions. Synthesis is running at `build/kyber-pipelined-hardware`;
this branch has not replaced the measured main implementation yet.

The pipelined Kyber synthesis now passes setup at 4 ns: 17056 LUTs, 9585 FFs,
three DSPs, three BRAM tiles and WNS +1.718 ns. The unchanged arithmetic oracle
passes at 1414 transaction cycles, and a separate reset regression aborts during
fetch/read/arithmetic/retirement and late execution, checks no stale completion,
and verifies fresh zero-frame results after restart on both banks/directions.
The change is integrated into main. Its synthesis hold estimate remains
-0.075 ns; this is not routed closure.

`build/kyber-pipeline-threeway-comparison` retains extracted, pre-pipeline,
and pipelined evidence together. Pipeline versus prior main trades seven
transaction cycles and 129 FFs for 6109 fewer LUTs, three fewer DSPs, and setup
closure. The extracted reference still has much lower area at the same cycle
count. Reducing replicated storage remains an open architecture task.
