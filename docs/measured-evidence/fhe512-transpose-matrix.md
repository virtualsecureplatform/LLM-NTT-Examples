# N=512 boundary-transpose comparison

All rows are exact 32-bit-torus negacyclic polynomial products with radix 2, Barrett reduction, baseline profile, and one stage group. 12/12 rows passed the 12-frame RTL product check. `—` means Yosys did not produce a cell count. Cells are coarse Yosys operators after memory lowering, not U280 LUTs; throughput is products per 1,000 cycles without an assumed clock.

| Backend | Lanes | PE | Boundary | Error bound | Observed error | Yosys cells | Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| streamed | 2 | 1 | indexed | 0 | 0 | 1,849,587 | 8,067 | 3,390 | 0.295 | screened |
| streamed | 2 | 1 | switch | 0 | 0 | 3,941,550 | 8,585 | 3,906 | 0.256 | screened |
| streamed | 2 | 2 | indexed | 0 | 0 | 1,875,903 | 5,252 | 1,983 | 0.504 | screened |
| streamed | 2 | 2 | switch | 0 | 0 | 3,967,110 | 5,770 | 2,499 | 0.400 | screened |
| streamed | 4 | 1 | indexed | 0 | 0 | 4,642,020 | 7,299 | 3,134 | 0.319 | screened |
| streamed | 4 | 1 | switch | 0 | 0 | 8,803,581 | 7,561 | 3,394 | 0.295 | screened |
| streamed | 4 | 2 | indexed | 0 | 0 | 4,650,453 | 4,484 | 1,727 | 0.579 | screened |
| streamed | 4 | 2 | switch | 0 | 0 | 8,812,014 | 4,746 | 1,987 | 0.503 | screened |
| stage-parallel | 2 | — | indexed | 0 | 0 | — | 1,818 | 521 | 1.919 | Yosys timeout (~7200s) |
| stage-parallel | 2 | — | switch | 0 | 0 | — | 2,846 | 1,037 | 0.964 | Yosys timeout (~7200s) |
| stage-parallel | 4 | — | indexed | 0 | 0 | — | 1,306 | 256 | 3.906 | Yosys timeout (~7200s) |
| stage-parallel | 4 | — | switch | 0 | 0 | — | 1,822 | 525 | 1.905 | Yosys timeout (~7200s) |
