# N=512 reduction and boundary-transpose comparison

All rows are exact 32-bit-torus negacyclic polynomial products with radix 2, Barrett/Montgomery/Shoup reductions, baseline profile, and one stage group. 28/28 rows passed the 12-frame RTL product check. `—` means Yosys did not produce a cell count. Cells are coarse Yosys operators after memory lowering, not U280 LUTs; throughput is products per 1,000 cycles without an assumed clock.

| Backend | Lanes | PE | Reduction | Boundary | Error bound | Observed error | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| streamed | 2 | 1 | barrett | indexed | 0 | 0 | 1,849,587 | 8,067 | 3,390 | 0.295 | screened |
| streamed | 2 | 1 | barrett | switch | 0 | 0 | 3,941,550 | 8,585 | 3,906 | 0.256 | screened |
| streamed | 2 | 1 | montgomery | indexed | 0 | 0 | 1,849,884 | 8,147 | 3,430 | 0.292 | screened |
| streamed | 2 | 1 | montgomery | switch | 0 | 0 | 3,941,847 | 8,665 | 3,946 | 0.253 | screened |
| streamed | 2 | 1 | shoup | indexed | 0 | 0 | 1,849,578 | 8,067 | 3,390 | 0.295 | screened |
| streamed | 2 | 1 | shoup | switch | 0 | 0 | 3,941,541 | 8,585 | 3,906 | 0.256 | screened |
| streamed | 2 | 2 | barrett | indexed | 0 | 0 | 1,875,903 | 5,252 | 1,983 | 0.504 | screened |
| streamed | 2 | 2 | barrett | switch | 0 | 0 | 3,967,110 | 5,770 | 2,499 | 0.400 | screened |
| streamed | 4 | 1 | barrett | indexed | 0 | 0 | 4,642,020 | 7,299 | 3,134 | 0.319 | screened |
| streamed | 4 | 1 | barrett | switch | 0 | 0 | 8,803,581 | 7,561 | 3,394 | 0.295 | screened |
| streamed | 4 | 1 | montgomery | indexed | 0 | 0 | 4,642,317 | 7,379 | 3,174 | 0.315 | screened |
| streamed | 4 | 1 | montgomery | switch | 0 | 0 | 8,803,878 | 7,641 | 3,434 | 0.291 | screened |
| streamed | 4 | 1 | shoup | indexed | 0 | 0 | 4,642,011 | 7,299 | 3,134 | 0.319 | screened |
| streamed | 4 | 1 | shoup | switch | 0 | 0 | 8,803,572 | 7,561 | 3,394 | 0.295 | screened |
| streamed | 4 | 2 | barrett | indexed | 0 | 0 | 4,650,453 | 4,484 | 1,727 | 0.579 | screened |
| streamed | 4 | 2 | barrett | switch | 0 | 0 | 8,812,014 | 4,746 | 1,987 | 0.503 | screened |
| stage-parallel | 2 | — | barrett | indexed | 0 | 0 | 1,943,319 | 1,818 | 521 | 1.919 | screened |
| stage-parallel | 2 | — | barrett | switch | 0 | 0 | 4,036,146 | 2,846 | 1,037 | 0.964 | screened |
| stage-parallel | 2 | — | montgomery | indexed | 0 | 0 | 1,818,831 | 1,818 | 521 | 1.919 | screened |
| stage-parallel | 2 | — | montgomery | switch | 0 | 0 | 3,911,658 | 2,846 | 1,037 | 0.964 | screened |
| stage-parallel | 2 | — | shoup | indexed | 0 | 0 | 1,833,987 | 1,818 | 521 | 1.919 | screened |
| stage-parallel | 2 | — | shoup | switch | 0 | 0 | 3,926,814 | 2,846 | 1,037 | 0.964 | screened |
| stage-parallel | 4 | — | barrett | indexed | 0 | 0 | 4,701,051 | 1,306 | 256 | 3.906 | screened |
| stage-parallel | 4 | — | barrett | switch | 0 | 0 | 8,866,410 | 1,822 | 525 | 1.905 | screened |
| stage-parallel | 4 | — | montgomery | indexed | 0 | 0 | 4,576,491 | 1,306 | 256 | 3.906 | screened |
| stage-parallel | 4 | — | montgomery | switch | 0 | 0 | 8,741,850 | 1,822 | 525 | 1.905 | screened |
| stage-parallel | 4 | — | shoup | indexed | 0 | 0 | 4,591,443 | 1,306 | 256 | 3.906 | screened |
| stage-parallel | 4 | — | shoup | switch | 0 | 0 | 8,756,802 | 1,822 | 525 | 1.905 | screened |
