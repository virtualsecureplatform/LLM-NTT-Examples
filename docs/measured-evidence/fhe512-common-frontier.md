# N=512 common-pass NGen/SGen Pareto screening

46/46 tested configurations completed the memory-collected Yosys 0.50 pass. All products have near-full-range signed 32-bit inputs and outputs modulo 2^32.

A point dominates another when it is no worse in all seven columns: analytical coefficient-error bound, generic cells, retained memory bits, register bits, multiplier operators, latency cycles, and frame interval cycles; and is strictly better in at least one. Smaller is better for every column. Products per 1,000 cycles equals 1,000 divided by frame interval, so it is not an independent objective. These resources are coarse Yosys estimates, not U280 utilization or a timing-qualified throughput.

Full frontier: **13** points; exact frontier: **11** points; error-at-most-8 frontier: **11** points.

Configuration controls are separate columns. The short ID links each row to the full RTL name and hash in the CSV and JSON evidence. A dash means the control does not apply to that generator.

## Full frontier

### NGen

| ID | Backend | Lanes | PE | Radix | Stage groups | Reduction | Profile | Boundary | Output round bits | Error bound | Cells | Memory bits | Register bits | Multipliers | Latency | Frame interval | Products / 1,000 cycles |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| N03 | stage-parallel | 2 | 1 | 2 | 1 | montgomery | baseline | indexed | 0 | 0 | 656,424 | 591,360 | 128,985 | 62,454 | 1,818 | 521 | 1.919386 |
| N05 | stage-parallel | 2 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 660,870 | 591,360 | 128,985 | 62,400 | 1,818 | 521 | 1.919386 |
| N10 | stage-parallel | 4 | 1 | 2 | 1 | montgomery | baseline | indexed | 0 | 0 | 657,513 | 591,360 | 131,226 | 62,760 | 1,306 | 256 | 3.906250 |
| N12 | stage-parallel | 4 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 661,797 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 |
| N21 | streamed | 2 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 18,963 | 3,192,708 | 28,128 | 111 | 8,067 | 3,390 | 0.294985 |
| N23 | streamed | 2 | 1 | 2 | 2 | barrett | baseline | indexed | 0 | 0 | 34,578 | 3,429,252 | 48,858 | 138 | 9,097 | 2,080 | 0.480769 |
| N25 | streamed | 2 | 2 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 44,892 | 3,193,344 | 46,623 | 138 | 5,252 | 1,983 | 0.504286 |
| N33 | streamed | 4 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 53,505 | 3,192,708 | 33,609 | 255 | 7,299 | 3,134 | 0.319081 |
| N37 | streamed | 4 | 2 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 62,973 | 3,193,344 | 48,864 | 282 | 4,484 | 1,727 | 0.579039 |
| N39 | streamed | 4 | 2 | 8 | 1 | barrett | baseline | indexed | 0 | 0 | 979,920 | 6,779,904 | 138,507 | 1,362 | 4,236 | 2,113 | 0.473261 |

### SGen

| ID | Backend | Lanes | FFT fractional bits | Guard bits | Omitted diagonals | Error bound | Cells | Memory bits | Register bits | Multipliers | Latency | Frame interval | Products / 1,000 cycles |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S01 | compact | 2 | 30 | 0 | 0 | 0 | 48,381 | 2,984,560 | 294,915 | 74 | 511,711 | 505,844 | 0.001977 |
| S02 | compact | 2 | 30 | 0 | 1 | 115,200 | 48,381 | 2,984,560 | 294,915 | 74 | 497,674 | 491,807 | 0.002033 |
| S03 | compact | 2 | 30 | 0 | 2 | 3,801,600 | 48,381 | 2,984,560 | 294,915 | 74 | 469,600 | 463,733 | 0.002156 |


## All tested configurations

Status `screened` means the existing RTL product check and this common Yosys pass both completed. The SGen 24-bit rejected control is listed in the [precision evidence](fhe512-sgen-precision.md), outside the eligible set.

### NGen

| ID | Backend | Lanes | PE | Radix | Stage groups | Reduction | Profile | Boundary | Output round bits | Error bound | Cells | Memory bits | Register bits | Multipliers | Latency | Frame interval | Products / 1,000 cycles | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| N01 | stage-parallel | 2 | 1 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 762,552 | 591,360 | 128,985 | 62,400 | 1,818 | 521 | 1.919386 | screened |
| N02 | stage-parallel | 2 | 1 | 2 | 1 | barrett | baseline | switch | 0 | 0 | 770,931 | 1,064,448 | 144,402 | 62,976 | 2,846 | 1,037 | 0.964320 | screened |
| N03 | stage-parallel | 2 | 1 | 2 | 1 | montgomery | baseline | indexed | 0 | 0 | 656,424 | 591,360 | 128,985 | 62,454 | 1,818 | 521 | 1.919386 | screened |
| N04 | stage-parallel | 2 | 1 | 2 | 1 | montgomery | baseline | switch | 0 | 0 | 664,803 | 1,064,448 | 144,402 | 63,030 | 2,846 | 1,037 | 0.964320 | screened |
| N05 | stage-parallel | 2 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 660,870 | 591,360 | 128,985 | 62,400 | 1,818 | 521 | 1.919386 | screened |
| N06 | stage-parallel | 2 | 1 | 2 | 1 | shoup | baseline | switch | 0 | 0 | 669,249 | 1,064,448 | 144,402 | 62,976 | 2,846 | 1,037 | 0.964320 | screened |
| N07 | stage-parallel | 4 | 1 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 763,785 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 | screened |
| N08 | stage-parallel | 4 | 1 | 2 | 1 | barrett | baseline | indexed | 4 | 8 | 782,076 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 | screened |
| N09 | stage-parallel | 4 | 1 | 2 | 1 | barrett | baseline | switch | 0 | 0 | 778,536 | 1,064,448 | 159,567 | 63,804 | 1,822 | 525 | 1.904762 | screened |
| N10 | stage-parallel | 4 | 1 | 2 | 1 | montgomery | baseline | indexed | 0 | 0 | 657,513 | 591,360 | 131,226 | 62,760 | 1,306 | 256 | 3.906250 | screened |
| N11 | stage-parallel | 4 | 1 | 2 | 1 | montgomery | baseline | switch | 0 | 0 | 672,264 | 1,064,448 | 159,567 | 63,912 | 1,822 | 525 | 1.904762 | screened |
| N12 | stage-parallel | 4 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 661,797 | 591,360 | 131,226 | 62,652 | 1,306 | 256 | 3.906250 | screened |
| N13 | stage-parallel | 4 | 1 | 2 | 1 | shoup | baseline | switch | 0 | 0 | 676,548 | 1,064,448 | 159,567 | 63,804 | 1,822 | 525 | 1.904762 | screened |
| N14 | streamed | 2 | 1 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 19,008 | 3,192,708 | 28,821 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| N15 | streamed | 2 | 1 | 2 | 1 | barrett | baseline | indexed | 4 | 8 | 19,011 | 3,192,708 | 28,821 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| N16 | streamed | 2 | 1 | 2 | 1 | barrett | baseline | switch | 0 | 0 | 26,487 | 3,665,796 | 44,238 | 687 | 8,585 | 3,906 | 0.256016 | screened |
| N17 | streamed | 2 | 1 | 2 | 1 | barrett | f300 | indexed | 0 | 0 | 19,008 | 3,192,708 | 28,821 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| N18 | streamed | 2 | 1 | 2 | 1 | montgomery | baseline | indexed | 0 | 0 | 19,305 | 3,192,708 | 34,932 | 111 | 8,147 | 3,430 | 0.291545 | screened |
| N19 | streamed | 2 | 1 | 2 | 1 | montgomery | baseline | indexed | 4 | 8 | 19,308 | 3,192,708 | 34,932 | 111 | 8,147 | 3,430 | 0.291545 | screened |
| N20 | streamed | 2 | 1 | 2 | 1 | montgomery | baseline | switch | 0 | 0 | 26,784 | 3,665,796 | 50,349 | 687 | 8,665 | 3,946 | 0.253421 | screened |
| N21 | streamed | 2 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 18,963 | 3,192,708 | 28,128 | 111 | 8,067 | 3,390 | 0.294985 | screened |
| N22 | streamed | 2 | 1 | 2 | 1 | shoup | baseline | switch | 0 | 0 | 26,442 | 3,665,796 | 43,545 | 687 | 8,585 | 3,906 | 0.256016 | screened |
| N23 | streamed | 2 | 1 | 2 | 2 | barrett | baseline | indexed | 0 | 0 | 34,578 | 3,429,252 | 48,858 | 138 | 9,097 | 2,080 | 0.480769 | screened |
| N24 | streamed | 2 | 1 | 8 | 1 | barrett | baseline | indexed | 0 | 0 | 197,640 | 6,772,464 | 73,548 | 651 | 7,686 | 4,219 | 0.237023 | screened |
| N25 | streamed | 2 | 2 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 44,892 | 3,193,344 | 46,623 | 138 | 5,252 | 1,983 | 0.504286 | screened |
| N26 | streamed | 2 | 2 | 2 | 1 | barrett | baseline | switch | 0 | 0 | 51,615 | 3,666,432 | 62,040 | 714 | 5,770 | 2,499 | 0.400160 | screened |
| N27 | streamed | 2 | 2 | 8 | 1 | barrett | baseline | indexed | 0 | 0 | 868,635 | 6,779,904 | 136,266 | 1,218 | 5,004 | 2,113 | 0.473261 | screened |
| N28 | streamed | 4 | 1 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 53,550 | 3,192,708 | 34,302 | 255 | 7,299 | 3,134 | 0.319081 | screened |
| N29 | streamed | 4 | 1 | 2 | 1 | barrett | baseline | switch | 0 | 0 | 64,467 | 3,665,796 | 62,643 | 1,407 | 7,561 | 3,394 | 0.294638 | screened |
| N30 | streamed | 4 | 1 | 2 | 1 | barrett | f300 | indexed | 0 | 0 | 53,550 | 3,192,708 | 34,302 | 255 | 7,299 | 3,134 | 0.319081 | screened |
| N31 | streamed | 4 | 1 | 2 | 1 | montgomery | baseline | indexed | 0 | 0 | 53,847 | 3,192,708 | 40,413 | 255 | 7,379 | 3,174 | 0.315060 | screened |
| N32 | streamed | 4 | 1 | 2 | 1 | montgomery | baseline | switch | 0 | 0 | 64,764 | 3,665,796 | 68,754 | 1,407 | 7,641 | 3,434 | 0.291206 | screened |
| N33 | streamed | 4 | 1 | 2 | 1 | shoup | baseline | indexed | 0 | 0 | 53,505 | 3,192,708 | 33,609 | 255 | 7,299 | 3,134 | 0.319081 | screened |
| N34 | streamed | 4 | 1 | 2 | 1 | shoup | baseline | switch | 0 | 0 | 64,422 | 3,665,796 | 61,950 | 1,407 | 7,561 | 3,394 | 0.294638 | screened |
| N35 | streamed | 4 | 1 | 2 | 2 | barrett | baseline | indexed | 0 | 0 | 103,401 | 3,429,252 | 58,041 | 282 | 7,817 | 1,824 | 0.548246 | screened |
| N36 | streamed | 4 | 1 | 8 | 1 | barrett | baseline | indexed | 0 | 0 | 239,139 | 6,772,464 | 75,789 | 795 | 6,918 | 4,219 | 0.237023 | screened |
| N37 | streamed | 4 | 2 | 2 | 1 | barrett | baseline | indexed | 0 | 0 | 62,973 | 3,193,344 | 48,864 | 282 | 4,484 | 1,727 | 0.579039 | screened |
| N38 | streamed | 4 | 2 | 2 | 1 | barrett | baseline | switch | 0 | 0 | 73,890 | 3,666,432 | 77,205 | 1,434 | 4,746 | 1,987 | 0.503271 | screened |
| N39 | streamed | 4 | 2 | 8 | 1 | barrett | baseline | indexed | 0 | 0 | 979,920 | 6,779,904 | 138,507 | 1,362 | 4,236 | 2,113 | 0.473261 | screened |
| N40 | streamed | 4 | 2 | 8 | 1 | barrett | baseline | indexed | 4 | 8 | 979,923 | 6,779,904 | 138,507 | 1,362 | 4,236 | 2,113 | 0.473261 | screened |

### SGen

| ID | Backend | Lanes | FFT fractional bits | Guard bits | Omitted diagonals | Error bound | Cells | Memory bits | Register bits | Multipliers | Latency | Frame interval | Products / 1,000 cycles | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S01 | compact | 2 | 30 | 0 | 0 | 0 | 48,381 | 2,984,560 | 294,915 | 74 | 511,711 | 505,844 | 0.001977 | screened |
| S02 | compact | 2 | 30 | 0 | 1 | 115,200 | 48,381 | 2,984,560 | 294,915 | 74 | 497,674 | 491,807 | 0.002033 | screened |
| S03 | compact | 2 | 30 | 0 | 2 | 3,801,600 | 48,381 | 2,984,560 | 294,915 | 74 | 469,600 | 463,733 | 0.002156 | screened |
| S04 | compact | 2 | 32 | 0 | 0 | 0 | 48,381 | 3,066,480 | 295,953 | 74 | 511,711 | 505,844 | 0.001977 | screened |
| S05 | compact | 2 | 32 | 0 | 1 | 115,200 | 48,381 | 3,066,480 | 295,953 | 74 | 497,674 | 491,807 | 0.002033 | screened |
| S06 | compact | 2 | 32 | 0 | 2 | 3,801,600 | 48,381 | 3,066,480 | 295,953 | 74 | 469,600 | 463,733 | 0.002156 | screened |
