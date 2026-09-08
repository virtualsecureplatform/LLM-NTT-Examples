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
