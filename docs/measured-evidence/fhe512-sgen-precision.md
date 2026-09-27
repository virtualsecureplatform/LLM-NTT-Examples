# N=512 SGen torus-product precision sweep

Input coefficients are in [-2147483647, 2147483647]; outputs are modulo 2^32. The exploratory coefficient-error limit is 4,000,000 torus units. Each complete product uses two input and output lanes and the compact SGen FFT. A lower-digit omission removes exact radix-16 digit products from the serial schedule. The reported worst-case bound covers that omission; it is not an FHE noise budget.

Coarse Yosys cells retain memory macros; memory bits and register bits are separate resource measures. These are not U280 LUTs or BRAMs. Throughput is products per 1,000 cycles without an assumed clock.

| Fractional bits | Omitted low diagonals | Digit products | Error bound | Observed max error | RMS error | Yosys cells | Memory bits | Register bits | Multipliers | Latency cycles | Frame interval cycles | Products / 1,000 cycles | Status |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 24 | 0 | 36 | — | — | — | — | — | — | — | — | — | — | numerical certificate or error limit rejected |
| 30 | 0 | 36 | 0 | 0 | 0.00 | 48,381 | 2,984,560 | 294,915 | 74 | 511,711 | 505,844 | 0.002 | screened |
| 30 | 1 | 35 | 115,200 | 115,200 | 42071.99 | 48,381 | 2,984,560 | 294,915 | 74 | 497,674 | 491,807 | 0.002 | screened |
| 30 | 2 | 33 | 3,801,600 | 3,801,600 | 1385612.49 | 48,381 | 2,984,560 | 294,915 | 74 | 469,600 | 463,733 | 0.002 | screened |
| 32 | 0 | 36 | 0 | 0 | 0.00 | 48,381 | 3,066,480 | 295,953 | 74 | 511,711 | 505,844 | 0.002 | screened |
| 32 | 1 | 35 | 115,200 | 115,200 | 42071.99 | 48,381 | 3,066,480 | 295,953 | 74 | 497,674 | 491,807 | 0.002 | screened |
| 32 | 2 | 33 | 3,801,600 | 3,801,600 | 1385612.49 | 48,381 | 3,066,480 | 295,953 | 74 | 469,600 | 463,733 | 0.002 | screened |
