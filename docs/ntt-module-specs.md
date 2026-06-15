# NTT Module Specifications

This document specifies the observable behavior required from the extracted NTT
top modules in this repository. It is written to be concrete enough for an LLM
to generate replacement Verilog that passes the current Verilator C++ tests.

The tests use TFHEpp as the C++ reference implementation. The TFHEpp submodule
is expected at `third_party/TFHEpp`.

## Common Requirements

- All top modules use a positive-edge `clock`.
- Top modules with a `reset` port use active-high reset. The C++ tests hold
  reset high for two cycles and then deassert it.
- Unspecified internal module names are not observable by the tests.
- Generated Verilog must keep the top module names and top-level port names
  listed here.
- If a module produces a streaming output, the exact pipeline latency may vary
  as long as the first `validout` arrives before the test watchdog expires and
  the output stream has the exact number of valid cycles required below.
- Arithmetic reference behavior is defined by the TFHEpp functions named in
  each module section.
- Wide packed ports use little-endian coefficient packing: coefficient or lane
  0 occupies the least significant bits of the packed port.

## Why These Prime Forms Are NTT Friendly

An NTT performs FFT-like butterfly operations over a finite field. For a prime
modulus `P`, the nonzero field elements form a multiplicative group of size
`P - 1`. A root of unity of order `M` exists when `M` divides `P - 1`.

The extracted designs use twisted, negacyclic NTTs for polynomial arithmetic
modulo `x^N + 1`. This normally requires a primitive `2N`-th root `psi` such
that:

```text
psi^(2N) = 1
psi^N = -1 mod P
omega = psi^2 is an N-th root of unity
```

Therefore, an NTT-friendly prime for these modules should satisfy:

```text
2N divides P - 1
```

Both extracted designs choose primes with a large power-of-two factor in
`P - 1`. This makes the required power-of-two roots of unity available and also
supports the staged radix structure used by the RTL.

### YATA RAINTT Prime

YATA uses:

```text
P = (5^4 << 16) + 1
  = 625 * 2^16 + 1
  = 40960001
P - 1 = 5^4 * 2^16
```

This is good for the YATA `N = 512` twisted NTT because:

- The transform needs `2N = 1024 = 2^10` to divide `P - 1`.
- `P - 1` contains `2^16`, so it has more than enough power-of-two order for
  the full transform and its internal stages.
- The extra `5^4` factor matches the compressed RAINTT parameterization
  (`K = 625`) used by the YATA design.
- `P` fits in 27 bits. Centered signed residues fit in the 27-bit datapath, and
  products of two residues fit comfortably in 64-bit intermediates.
- The form `K * 2^16 + 1` makes the modulus directly tied to shift-based
  scaling and root generation: powers of two are cheap in hardware, while the
  small odd factor keeps the prime compact.

For LLM-generated Verilog, the important invariant is not just the numeric value
of `P`, but the divisibility:

```text
2 * 512 = 1024 divides 40960001 - 1
```

### HOGE 64-Bit Prime

HOGE uses:

```text
P = 0xffffffff00000001
  = 2^64 - 2^32 + 1
P - 1 = 2^32 * (2^32 - 1)
      = 2^32 * 3 * 5 * 17 * 257 * 65537
```

This is good for the HOGE `N = 1024` twisted NTT because:

- The transform needs `2N = 2048 = 2^11` to divide `P - 1`.
- `P - 1` contains `2^32`, so it supports power-of-two roots far larger than
  the current 1024-coefficient transforms.
- `P` is close to the 64-bit word size, so each field element fits in one
  unsigned 64-bit word while still leaving an NTT-friendly root structure.
- Modular reduction can exploit:

```text
2^64 = 2^32 - 1 mod P
```

  A 128-bit product can be reduced by folding high limbs with shifts, adds, and
  subtracts instead of a general division.
- The large field is convenient for the HOGE path, where 32-bit torus inputs are
  expanded into 64-bit NTT-domain residues.

For LLM-generated Verilog, the important invariant is:

```text
2 * 1024 = 2048 divides 0xffffffff00000001 - 1
```

The C++ tests compare against TFHEpp, so generated arithmetic RTL should use the
same roots and twist tables as TFHEpp for these primes. If the implementation is
simulation-oriented, it may compute the same observable transform by any method,
but the modular field and stream ordering must remain exactly as specified.

## YataRainttTop

### Source And Test

- RTL source: `variants/yata-raintt/chisel/src/main/scala`
- Generated Verilog used by the test:
  `variants/yata-raintt/chisel/YataRainttTop.v`
- C++ test: `tests/cpp/yata_raintt_reference_test.cpp`
- CMake test name: `yata_raintt_reference_test`

### Parameters

| Name | Value | Meaning |
| --- | ---: | --- |
| `Nbit` | 9 | log2 polynomial size |
| `N` | 512 | polynomial coefficients |
| `nttsizebit` | 6 | log2 lanes per stream cycle |
| `nttsize` | 64 | lanes per stream cycle |
| `cyclebit` | 3 | log2 stream cycles |
| `numcycle` | 8 | cycles per full polynomial |
| `radixbit` | 3 | RAINTT radix log2 |
| `radix` | 8 | RAINTT radix |
| `rk` | 5 | RAINTT compressed modulus factor |
| `radixs2` | 4 | shift radix log2 |
| `shiftunit` | 4 | compressed shift unit |
| `shiftamount` | 16 | compressed shift amount |
| `K` | 625 | `5^4` |
| `P` | 40960001 | compressed RAINTT modulus, `(K << 16) + 1` |
| `wordbits` | 27 | signed internal coefficient width |
| `Qbit` | 32 | torus input and output width |
| `muldelay` | 3 | original multiplier pipeline delay |
| `radixdelay` | 7 | original radix pipeline delay |

### Top-Level Interface

The generated Verilog module must be named `YataRainttTop`.

| Port | Direction | Width | Description |
| --- | --- | ---: | --- |
| `clock` | input | 1 | clock |
| `reset` | input | 1 | active-high reset |
| `io_intt_validin` | input | 1 | input valid for INTT stream |
| `io_intt_validout` | output | 1 | output valid for INTT stream |
| `io_intt_in_0` ... `io_intt_in_63` | input | 32 each | INTT input lanes |
| `io_intt_out_0` ... `io_intt_out_63` | output | 27 each signed | INTT output lanes |
| `io_ntt_validin` | input | 1 | input valid for NTT stream |
| `io_ntt_validout` | output | 1 | output valid for NTT stream |
| `io_ntt_in_0` ... `io_ntt_in_63` | input | 27 each signed | NTT input lanes |
| `io_ntt_out_0` ... `io_ntt_out_63` | output | 32 each | NTT output lanes |

The Verilator C++ test accesses the lane ports by their flattened Chisel names,
for example `dut.io_ntt_in_17` and `dut.io_ntt_out_17`.

### Reset Behavior

During reset:

- Both valid inputs are held low by the test.
- All input lanes are driven to zero by the test.
- The design must clear enough internal state that a transaction started after
  reset produces deterministic output.

### INTT Observable Behavior

The INTT path is checked against TFHEpp exactly.

Input transaction:

- The test drives `io_intt_validin = 1` for 8 consecutive clock cycles.
- On input cycle `c` in `0..7` and lane `l` in `0..63`, the lane carries
  polynomial coefficient index `l * 8 + c`.
- After 8 input cycles, the test drives `io_intt_validin = 0`.

Output transaction:

- `io_intt_validout` must assert within 2000 cycles after the input stream.
- Once asserted for this transaction, `io_intt_validout` must stay high for
  exactly 8 consecutive output cycles.
- On output cycle `c` in `0..7` and lane `l` in `0..63`, `io_intt_out_l`
  must equal TFHEpp expected coefficient index `c * 64 + l`.

The exact reference is:

```text
table = TFHEpp::raintt::TableGen<9>()
twist = TFHEpp::raintt::TwistGen<9, 3>()
fd = TFHEpp::raintt::TwistINTT<uint32_t, 9, false>(poly, table[1], twist[1])
```

### NTT Observable Behavior

The NTT path is checked against TFHEpp exactly.

Input transaction:

- The test first computes a signed 27-bit domain vector `fd[0..511]` with
  TFHEpp RAINTT inverse transform:

```text
table = TFHEpp::raintt::TableGen<9>()
twist = TFHEpp::raintt::TwistGen<9, 3>()
fd = TFHEpp::raintt::TwistINTT<uint32_t, 9, false>(poly, table[1], twist[1])
```

- The test drives `io_ntt_validin = 1` for 8 consecutive clock cycles.
- On input cycle `c` in `0..7` and lane `l` in `0..63`, the lane carries
  `fd[c * 64 + l]`.
- Each lane is a signed 27-bit two's-complement value. In the C++ test, it is
  assigned by masking with `(1 << 27) - 1`.
- After 8 input cycles, the test drives `io_ntt_validin = 0`.

Output transaction:

- `io_ntt_validout` must assert within 2000 cycles after the input stream.
- Once asserted for this transaction, `io_ntt_validout` must stay high for
  exactly 8 consecutive output cycles.
- Output ordering is transposed relative to the input stream.
- On output cycle `c` in `0..7` and lane `l` in `0..63`,
  `io_ntt_out_l` must equal TFHEpp expected coefficient index `l * 8 + c`.

The exact reference is:

```text
expected = TFHEpp::raintt::TwistNTT<uint32_t, 9, true>(fd, table[1], twist[1])
expected_index = lane * 8 + output_cycle
io_ntt_out_lane == expected[expected_index]
```

### Test Vectors

The current C++ test runs four polynomials:

- `poly[i] = i % P`
- `poly[i] = 0` for even `i`, `P - 1` for odd `i`
- Two random vectors with coefficients in `[0, P - 1]` using seed `0x4c4c4d`

## Hoge Streaming INTTWrap

### Source And Test

- RTL source: `variants/hoge-streaming/chisel/src/main/scala`
- Generated Verilog used by the test:
  `variants/hoge-streaming/chisel/INTTWrap.v`
- C++ test: `tests/cpp/hoge_streaming_reference_test.cpp`
- CMake test name: `hoge_streaming_reference_test`

### Parameters

| Name | Value | Meaning |
| --- | ---: | --- |
| `Nbit` | 10 | log2 polynomial size |
| `N` | 1024 | polynomial coefficients |
| `cyclebit` | 5 | log2 stream cycles |
| `numcycle` | 32 | cycles per full polynomial |
| `stepbit` | 1 | log2 transform steps |
| `numstep` | 2 | transform steps |
| `radixbit` | 5 | log2 lanes per stream cycle |
| `radix` | 32 | lanes per stream cycle |
| `block` | 32 | `N >> radixbit` |
| `chunk` | 1 | `block >> cyclebit` |
| `fiber` | 32 | `N >> cyclebit` |
| `P` | `0xffffffff00000001` | 64-bit NTT modulus |
| `W` | `12037493425763644479` | primitive root parameter |
| `qbit` | 32 | input torus width |
| `multiplierpipestage` | 7 | original multiplier pipeline stages |
| `muldelay` | 9 | original multiplier delay |
| `lshdelay` | 3 | original left-shift delay |
| `radixdelay` | 5 | original radix delay |

### Top-Level Interface

The generated Verilog module must be named `INTTWrap`.

| Port | Direction | Width | Description |
| --- | --- | ---: | --- |
| `clock` | input | 1 | clock |
| `reset` | input | 1 | active-high reset |
| `io_enable` | input | 1 | stream enable |
| `io_validout` | output | 1 | output valid |
| `io_in` | input | 1024 | packed 32-lane, 32-bit input vector |
| `io_out` | output | 2048 | packed 32-lane, 64-bit output vector |

Under Verilator, the packed ports are accessed as 32-bit word arrays:

- `io_in[0]` ... `io_in[31]`
- `io_out[0]` ... `io_out[63]`

Input lane `l` is stored in `io_in[l]`.

Output lane `l` is reconstructed as:

```text
out_lane_l = uint64(io_out[2 * l]) | (uint64(io_out[2 * l + 1]) << 32)
```

### Reset And Enable Behavior

- The test resets the module for two clock cycles with `io_enable = 0`.
- After reset, the test drives `io_enable = 1` for all input and output cycles.
- The design may ignore input cycles when `io_enable = 0`.
- For the tested transaction, all input cycles occur while `io_enable = 1`.

### Observable Behavior

Input transaction:

- The test drives 32 consecutive enabled input cycles.
- On input cycle `c` in `0..31` and lane `l` in `0..31`, the lane carries
  polynomial coefficient index `l * 32 + c`.
- This is a transposed input order relative to the natural coefficient order.

Reference computation:

```text
table = TFHEpp::cuHEpp::TableGen<10>()
twist = TFHEpp::cuHEpp::TwistGen<10>()
expected = TFHEpp::cuHEpp::TwistINTT<uint32_t, 10>(poly, table[1], twist[1])
```

Output transaction:

- `io_validout` must assert within 4000 cycles after the input stream begins.
- Once asserted for this transaction, `io_validout` must stay high for exactly
  32 consecutive output cycles.
- On output cycle `c` in `0..31` and lane `l` in `0..31`, output lane `l` must
  equal `expected[c * 32 + l].value`.
- Each output value is a 64-bit residue modulo `P`.

### Test Vectors

The current C++ test runs three polynomials:

- `poly[i] = i`
- Two random `uint32_t` vectors using seed `0x5354524d`

## Hoge Streaming NTTWrap

### Source And Test Coverage

- RTL source: `variants/hoge-streaming/chisel/src/main/scala`
- Generated Verilog:
  `variants/hoge-streaming/chisel/NTTWrap.v`
- There is no current C++ Verilator test for this top module. It is generated
  by the extraction flow and should elaborate successfully.

### Parameters

`NTTWrap` uses the same parameters as `INTTWrap` in the Hoge streaming variant.

### Top-Level Interface

The generated Verilog module must be named `NTTWrap`.

| Port | Direction | Width | Description |
| --- | --- | ---: | --- |
| `clock` | input | 1 | clock |
| `reset` | input | 1 | active-high reset |
| `io_enable` | input | 1 | stream enable |
| `io_ready` | output | 1 | input acceptance indicator |
| `io_validout` | output | 1 | output valid |
| `io_in` | input | 2048 | packed 32-lane, 64-bit input vector |
| `io_out` | output | 2048 | packed 32-lane, 64-bit output vector |

Under Verilator, each packed 2048-bit port is a 64-word array of 32-bit chunks.
Lane `l` is packed and unpacked as:

```text
lane_l = uint64(port[2 * l]) | (uint64(port[2 * l + 1]) << 32)
```

### Interface/Lint Contract

`NTTWrap` is an extracted internal forward-transform pipeline wrapper. The
current repository intentionally treats it as a `tier0_interface` task.

The executable contract is limited to:

- module name `NTTWrap`
- the ports and widths listed above
- successful Verilog elaboration with Verilator
- the packed-lane convention for `io_in` and `io_out`

The current task does not check:

- forward NTT arithmetic
- coefficient ordering
- latency or throughput
- `io_validout` burst length
- whether the standalone wrapper is equivalent to a TFHEpp API call

This distinction matters for architecture search. A candidate that passes
`hoge_streaming_ntt_1024_p64` has passed an interface/lint gate only; it should
not be ranked against correctness-tested NTT or INTT tasks for arithmetic
quality, latency, or resource efficiency.

### Planned ExternalProduct-Style Forward NTT Oracle

The original HOGE forward NTT correctness boundary is the final output check in
the HOGE `ExternalProduct` C++ test, not the standalone `NTTWrap` module. That
boundary emits 32-bit torus words after the final NTT/output path and compares
two result components against TFHEpp:

```text
TFHEpp::TwistNTT<P>(res[0], restrlwentt[0])
TFHEpp::TwistNTT<P>(res[1], restrlwentt[1])
```

The output capture order from that boundary is:

```text
circres[k][j * 32 + i] = io_out[j]
```

where `k` is the component index, `i` is the output cycle in `0..31`, and `j`
is the output lane in `0..31`.

A future executable forward-NTT task should extract or wrap that
ExternalProduct final-output boundary, drive the same 64-bit residue-domain
inputs, capture the 32-bit torus output in the order above, and compare every
coefficient against `TFHEpp::TwistNTT<P>`. The planned task skeleton is recorded
in `tasks/planned/hoge_externalproduct_ntt_1024_p64.json`; it is not runnable by
the current evaluator.

## Hoge NTTidPackedTop

### Source And Test

- RTL source: `variants/hoge-nttid/chisel/src/main/scala`
- Generated Verilog used by the test:
  `variants/hoge-nttid/chisel/NTTidPackedTop.v`
- C++ test: `tests/cpp/hoge_nttid_identity_test.cpp`
- CMake test name: `hoge_nttid_identity_test`

### Parameters

| Name | Value | Meaning |
| --- | ---: | --- |
| `Nbit` | 10 | log2 polynomial size |
| `N` | 1024 | polynomial coefficients |
| `cyclebit` | 3 | log2 internal cycles |
| `numcycle` | 8 | internal cycles per phase |
| `stepbit` | 1 | log2 transform steps |
| `numstep` | 2 | transform steps |
| `radixbit` | 5 | log2 radix |
| `radix` | 32 | radix |
| `block` | 32 | `N >> radixbit` |
| `chunk` | 4 | `block >> cyclebit` |
| `fiber` | 128 | `N >> cyclebit` |
| `P` | `0xffffffff00000001` | 64-bit NTT modulus |
| `W` | `12037493425763644479` | primitive root parameter |

### Top-Level Interface

The generated Verilog module must be named `NTTidPackedTop`.

| Port | Direction | Width | Description |
| --- | --- | ---: | --- |
| `clock` | input | 1 | clock |
| `reset` | input | 1 | active-high reset |
| `io_in` | input | 65536 | packed 1024-lane, 64-bit input vector |
| `io_out` | output | 65536 | packed 1024-lane, 64-bit output vector |

Under Verilator, each packed 65536-bit port is a 2048-word array of 32-bit
chunks. Coefficient `i` is packed and unpacked as:

```text
coeff_i = uint64(port[2 * i]) | (uint64(port[2 * i + 1]) << 32)
```

### Reset Behavior

- The test resets the module for two clock cycles with all input words zero.
- After reset, the test drives the full packed input vector and then waits.
- There is no valid or enable input on this top module.

### Observable Behavior

The current C++ test checks identity modulo `P`.

- The input is a complete static 1024-coefficient vector.
- The test waits 33 clock cycles after applying the input.
- At that point, for every coefficient index `i` in `0..1023`:

```text
io_out[i] mod P == io_in[i] mod P
```

- The output does not need to be in canonical range as long as reducing modulo
  `P` produces the input residue.
- The tested input values are non-negative 63-bit integers, so they are already
  less than `P`.

The original Chisel core alternates an inverse transform and a forward transform
internally. For the current testbench, the required observable result is the
combined identity transform after the wait period.

### Test Vectors

The current C++ test runs three packed vectors:

- `input[i] = i`
- `input[i] = (i * 2654435761) & ((1 << 63) - 1)`
- Random values `rng() & ((1 << 63) - 1)` using seed `0x4e545469`

## Generated Verilog Checklist

Use this checklist before running the tests:

- `YataRainttTop.v` defines module `YataRainttTop` with all flattened lane
  ports listed above.
- `INTTWrap.v` defines module `INTTWrap` with 1024-bit `io_in` and 2048-bit
  `io_out`.
- `NTTWrap.v` defines module `NTTWrap` with 2048-bit `io_in` and 2048-bit
  `io_out`.
- `NTTidPackedTop.v` defines module `NTTidPackedTop` with 65536-bit `io_in`
  and 65536-bit `io_out`.
- Streaming valid outputs have the exact stream lengths expected by the tests:
  8 cycles for `YataRainttTop` INTT and NTT, 32 cycles for `INTTWrap`.
- Yata INTT input ordering is `poly[lane * 8 + input_cycle]`.
- Yata INTT output ordering is `expected[output_cycle * 64 + lane]`.
- Yata NTT output ordering is `expected[lane * 8 + output_cycle]`.
- Hoge streaming INTT input ordering is `poly[lane * 32 + input_cycle]`.
- Hoge streaming INTT output ordering is `expected[output_cycle * 32 + lane]`.
- Hoge NTTid output is congruent to input modulo `0xffffffff00000001` after
  33 post-reset wait cycles.

## Test Commands

Generate Verilog, build, and run all tests natively:

```bash
./scripts/build_and_test.sh
```

Run through the Apptainer container:

```bash
apptainer build --mksquashfs-args "-processors 1" llm-ntt.sif apptainer/llm-ntt.def
apptainer run --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif
```
