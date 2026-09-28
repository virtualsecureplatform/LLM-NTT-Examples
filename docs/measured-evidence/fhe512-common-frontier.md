# N=512 common-pass NGen/SGen Pareto screening

46/46 tested configurations completed the memory-collected Yosys 0.50 pass. All products have near-full-range signed 32-bit inputs and outputs modulo 2^32.

A point dominates another when it is no worse in all seven columns: analytical coefficient-error bound, generic cells, retained memory bits, register bits, multiplier operators, latency cycles, and frame interval cycles; and is strictly better in at least one. Smaller is better for every column. Products per 1,000 cycles equals 1,000 divided by frame interval, so it is not an independent objective. These resources are coarse Yosys estimates, not U280 utilization or a timing-qualified throughput.

Full frontier: **13** points; exact frontier: **11** points; error-at-most-8 frontier: **11** points.

## Full frontier

| Configuration | Error bound | Cells | Memory bits | Register bits | Multipliers | Latency | Frame interval | Products / 1,000 cycles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ngen-stage-parallel-l2-pe1-r2-s1-montgomery-baseline-q0` | 0 | 656,424 | 591,360 | 128,985 | 62,454 | 1,818 | 521 | 1.919386 |
| `ngen-stage-parallel-l2-pe1-r2-s1-shoup-baseline-q0` | 0 | 660,870 | 591,360 | 128,985 | 62,400 | 1,818 | 521 | 1.919386 |
| `ngen-stage-parallel-l4-pe1-r2-s1-montgomery-baseline-q0` | 0 | 657,513 | 591,360 | 131,226 | 62,760 | 1,306 | 256 | 3.906250 |
| `ngen-stage-parallel-l4-pe1-r2-s1-shoup-baseline-q0` | 0 | 661,797 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 |
| `ngen-streamed-l2-pe1-r2-s1-shoup-baseline-q0` | 0 | 18,963 | 3,192,708 | 28,128 | 111 | 8,067 | 3,390 | 0.294985 |
| `ngen-streamed-l2-pe1-r2-s2-barrett-baseline-q0` | 0 | 34,578 | 3,429,252 | 48,858 | 138 | 9,097 | 2,080 | 0.480769 |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-q0` | 0 | 44,892 | 3,193,344 | 46,623 | 138 | 5,252 | 1,983 | 0.504286 |
| `ngen-streamed-l4-pe1-r2-s1-shoup-baseline-q0` | 0 | 53,505 | 3,192,708 | 33,609 | 255 | 7,299 | 3,134 | 0.319081 |
| `ngen-streamed-l4-pe2-r2-s1-barrett-baseline-q0` | 0 | 62,973 | 3,193,344 | 48,864 | 282 | 4,484 | 1,727 | 0.579039 |
| `ngen-streamed-l4-pe2-r8-s1-barrett-baseline-q0` | 0 | 979,920 | 6,779,904 | 138,507 | 1,362 | 4,236 | 2,113 | 0.473261 |
| `sgen-compact-l2-f30-g0` | 0 | 48,381 | 2,984,560 | 294,915 | 74 | 511,711 | 505,844 | 0.001977 |
| `sgen-compact-l2-f30-g0-omit1` | 115,200 | 48,381 | 2,984,560 | 294,915 | 74 | 497,674 | 491,807 | 0.002033 |
| `sgen-compact-l2-f30-g0-omit2` | 3,801,600 | 48,381 | 2,984,560 | 294,915 | 74 | 469,600 | 463,733 | 0.002156 |

## All tested configurations

Status `screened` means the existing RTL product check and this common Yosys pass both completed. The SGen 24-bit rejected control is listed in the [precision evidence](fhe512-sgen-precision.md), outside the eligible set.

| Configuration | Error bound | Cells | Memory bits | Register bits | Multipliers | Latency | Frame interval | Products / 1,000 cycles | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline-q0` | 0 | 762,552 | 591,360 | 128,985 | 62,400 | 1,818 | 521 | 1.919386 | screened |
| `ngen-stage-parallel-l2-pe1-r2-s1-barrett-baseline-switch-q0` | 0 | 770,931 | 1,064,448 | 144,402 | 62,976 | 2,846 | 1,037 | 0.964320 | screened |
| `ngen-stage-parallel-l2-pe1-r2-s1-montgomery-baseline-q0` | 0 | 656,424 | 591,360 | 128,985 | 62,454 | 1,818 | 521 | 1.919386 | screened |
| `ngen-stage-parallel-l2-pe1-r2-s1-montgomery-baseline-switch-q0` | 0 | 664,803 | 1,064,448 | 144,402 | 63,030 | 2,846 | 1,037 | 0.964320 | screened |
| `ngen-stage-parallel-l2-pe1-r2-s1-shoup-baseline-q0` | 0 | 660,870 | 591,360 | 128,985 | 62,400 | 1,818 | 521 | 1.919386 | screened |
| `ngen-stage-parallel-l2-pe1-r2-s1-shoup-baseline-switch-q0` | 0 | 669,249 | 1,064,448 | 144,402 | 62,976 | 2,846 | 1,037 | 0.964320 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q0` | 0 | 763,785 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-q4` | 8 | 782,076 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-barrett-baseline-switch-q0` | 0 | 778,536 | 1,064,448 | 159,567 | 63,804 | 1,822 | 525 | 1.904762 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-montgomery-baseline-q0` | 0 | 657,513 | 591,360 | 131,226 | 62,760 | 1,306 | 256 | 3.906250 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-montgomery-baseline-switch-q0` | 0 | 672,264 | 1,064,448 | 159,567 | 63,912 | 1,822 | 525 | 1.904762 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-shoup-baseline-q0` | 0 | 661,797 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 | screened |
| `ngen-stage-parallel-l4-pe1-r2-s1-shoup-baseline-switch-q0` | 0 | 676,548 | 1,064,448 | 159,567 | 63,804 | 1,822 | 525 | 1.904762 | screened |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-q0` | 0 | 19,008 | 3,192,708 | 28,821 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-q4` | 8 | 19,011 | 3,192,708 | 28,821 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| `ngen-streamed-l2-pe1-r2-s1-barrett-baseline-switch-q0` | 0 | 26,487 | 3,665,796 | 44,238 | 687 | 8,585 | 3,906 | 0.256016 | screened |
| `ngen-streamed-l2-pe1-r2-s1-barrett-f300-q0` | 0 | 19,008 | 3,192,708 | 28,821 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| `ngen-streamed-l2-pe1-r2-s1-montgomery-baseline-q0` | 0 | 19,305 | 3,192,708 | 34,932 | 111 | 8,147 | 3,430 | 0.291545 | screened |
| `ngen-streamed-l2-pe1-r2-s1-montgomery-baseline-q4` | 8 | 19,308 | 3,192,708 | 34,932 | 111 | 8,147 | 3,430 | 0.291545 | screened |
| `ngen-streamed-l2-pe1-r2-s1-montgomery-baseline-switch-q0` | 0 | 26,784 | 3,665,796 | 50,349 | 687 | 8,665 | 3,946 | 0.253421 | screened |
| `ngen-streamed-l2-pe1-r2-s1-shoup-baseline-q0` | 0 | 18,963 | 3,192,708 | 28,128 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| `ngen-streamed-l2-pe1-r2-s1-shoup-baseline-switch-q0` | 0 | 26,442 | 3,665,796 | 43,545 | 687 | 8,585 | 3,906 | 0.256016 | screened |
| `ngen-streamed-l2-pe1-r2-s2-barrett-baseline-q0` | 0 | 34,578 | 3,429,252 | 48,858 | 138 | 9,097 | 2,080 | 0.480769 | screened |
| `ngen-streamed-l2-pe1-r8-s1-barrett-baseline-q0` | 0 | 197,640 | 6,772,464 | 73,548 | 651 | 7,686 | 4,219 | 0.237023 | screened |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-q0` | 0 | 44,892 | 3,193,344 | 46,623 | 138 | 5,252 | 1,983 | 0.504286 | screened |
| `ngen-streamed-l2-pe2-r2-s1-barrett-baseline-switch-q0` | 0 | 51,615 | 3,666,432 | 62,040 | 714 | 5,770 | 2,499 | 0.400160 | screened |
| `ngen-streamed-l2-pe2-r8-s1-barrett-baseline-q0` | 0 | 868,635 | 6,779,904 | 136,266 | 1,218 | 5,004 | 2,113 | 0.473261 | screened |
| `ngen-streamed-l4-pe1-r2-s1-barrett-baseline-q0` | 0 | 53,550 | 3,192,708 | 34,302 | 255 | 7,299 | 3,134 | 0.319081 | screened |
| `ngen-streamed-l4-pe1-r2-s1-barrett-baseline-switch-q0` | 0 | 64,467 | 3,665,796 | 62,643 | 1,407 | 7,561 | 3,394 | 0.294638 | screened |
| `ngen-streamed-l4-pe1-r2-s1-barrett-f300-q0` | 0 | 53,550 | 3,192,708 | 34,302 | 255 | 7,299 | 3,134 | 0.319081 | screened |
| `ngen-streamed-l4-pe1-r2-s1-montgomery-baseline-q0` | 0 | 53,847 | 3,192,708 | 40,413 | 255 | 7,379 | 3,174 | 0.315060 | screened |
| `ngen-streamed-l4-pe1-r2-s1-montgomery-baseline-switch-q0` | 0 | 64,764 | 3,665,796 | 68,754 | 1,407 | 7,641 | 3,434 | 0.291206 | screened |
| `ngen-streamed-l4-pe1-r2-s1-shoup-baseline-q0` | 0 | 53,505 | 3,192,708 | 33,609 | 255 | 7,299 | 3,134 | 0.319081 | screened |
| `ngen-streamed-l4-pe1-r2-s1-shoup-baseline-switch-q0` | 0 | 64,422 | 3,665,796 | 61,950 | 1,407 | 7,561 | 3,394 | 0.294638 | screened |
| `ngen-streamed-l4-pe1-r2-s2-barrett-baseline-q0` | 0 | 103,401 | 3,429,252 | 58,041 | 282 | 7,817 | 1,824 | 0.548246 | screened |
| `ngen-streamed-l4-pe1-r8-s1-barrett-baseline-q0` | 0 | 239,139 | 6,772,464 | 75,789 | 795 | 6,918 | 4,219 | 0.237023 | screened |
| `ngen-streamed-l4-pe2-r2-s1-barrett-baseline-q0` | 0 | 62,973 | 3,193,344 | 48,864 | 282 | 4,484 | 1,727 | 0.579039 | screened |
| `ngen-streamed-l4-pe2-r2-s1-barrett-baseline-switch-q0` | 0 | 73,890 | 3,666,432 | 77,205 | 1,434 | 4,746 | 1,987 | 0.503271 | screened |
| `ngen-streamed-l4-pe2-r8-s1-barrett-baseline-q0` | 0 | 979,920 | 6,779,904 | 138,507 | 1,362 | 4,236 | 2,113 | 0.473261 | screened |
| `ngen-streamed-l4-pe2-r8-s1-barrett-baseline-q4` | 8 | 979,923 | 6,779,904 | 138,507 | 1,362 | 4,236 | 2,113 | 0.473261 | screened |
| `sgen-compact-l2-f30-g0` | 0 | 48,381 | 2,984,560 | 294,915 | 74 | 511,711 | 505,844 | 0.001977 | screened |
| `sgen-compact-l2-f30-g0-omit1` | 115,200 | 48,381 | 2,984,560 | 294,915 | 74 | 497,674 | 491,807 | 0.002033 | screened |
| `sgen-compact-l2-f30-g0-omit2` | 3,801,600 | 48,381 | 2,984,560 | 294,915 | 74 | 469,600 | 463,733 | 0.002156 | screened |
| `sgen-compact-l2-f32-g0` | 0 | 48,381 | 3,066,480 | 295,953 | 74 | 511,711 | 505,844 | 0.001977 | screened |
| `sgen-compact-l2-f32-g0-omit1` | 115,200 | 48,381 | 3,066,480 | 295,953 | 74 | 497,674 | 491,807 | 0.002033 | screened |
| `sgen-compact-l2-f32-g0-omit2` | 3,801,600 | 48,381 | 3,066,480 | 295,953 | 74 | 469,600 | 463,733 | 0.002156 | screened |
