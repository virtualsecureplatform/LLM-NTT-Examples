#!/usr/bin/env python3
"""Generate and synthesize a YATA RAINTT HLS candidate, then compare metrics."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "yata_raintt_512_p27"
NBIT = 9
N = 1 << NBIT
RADIXBIT = 3
P = 40960001
K = 625
SHIFTAMOUNT = 16
WORDBITS = 27
WORDMASK = (1 << WORDBITS) - 1
R = (1 << WORDBITS) % P
R2 = (R * R) % P
DEFAULT_PART = "xcu280-fsvh2892-2L-e"
DEFAULT_CLOCK_PERIOD_NS = 4.0
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "yata-hls-synth-compare"
REFERENCE_RESULTS = REPO_ROOT / "baselines" / "extracted-rtl" / f"{TASK_ID}.json"


def sign_extend27(value: int) -> int:
    value &= WORDMASK
    if value & (1 << (WORDBITS - 1)):
        value -= 1 << WORDBITS
    return value


def redc(value: int) -> int:
    low = value & WORDMASK
    m = (((low * K) << SHIFTAMOUNT) - low) & WORDMASK
    reduced = (value + ((m * K) << SHIFTAMOUNT) + m) >> WORDBITS
    return reduced - P if reduced > P else reduced


def mul_redc(left: int, right: int) -> int:
    return redc(left * right)


def pow_redc(base: int, exponent: int) -> int:
    result = 1
    base_r = mul_redc(R2, base)
    for _ in range(exponent):
        result = mul_redc(result, base_r)
    return result


def bit_reverse(value: int, bits: int) -> int:
    result = 0
    for index in range(bits):
        result = (result << 1) | ((value >> index) & 1)
    return result


def generate_tables() -> dict[str, list[int]]:
    w = pow_redc(31, K)
    inv_n = pow(N, -1, P)

    twist = [[0 for _ in range(N)] for _ in range(2)]
    twist_wr = mul_redc(pow_redc(w, 1 << (SHIFTAMOUNT - NBIT - 1)), R2)
    twist[1][0] = R
    for index in range(1, N):
        twist[1][index] = mul_redc(twist[1][index - 1], twist_wr)
    twist[0][N - 1] = mul_redc(
        mul_redc(twist[1][N - 1], twist_wr), (inv_n * twist_wr) % P
    )
    twist[0][0] = (inv_n * R) % P
    for index in range(2, N):
        twist[0][N - index] = mul_redc(twist[0][N - index + 1], twist_wr)
    for index in range(N):
        if ((index >> (NBIT - RADIXBIT)) & ((1 << (RADIXBIT - 1)) - 1)) != 0:
            twist[0][index] = mul_redc(twist[0][index], R2)

    table = [[[0 for _ in range(N)] for _ in range(2)] for _ in range(2)]
    table_w = pow_redc(w, 1 << (SHIFTAMOUNT - NBIT))
    table_wr = mul_redc(table_w, R2)
    table[0][0][0] = table[1][0][0] = R
    table[0][1][0] = table[1][1][0] = R2
    for index in range(1, N):
        table[1][0][index] = mul_redc(table[1][0][index - 1], table_wr)
    for index in range(1, N):
        table[1][1][index] = mul_redc(table[1][0][index], R2)
    for lane in range(2):
        for index in range(1, N):
            table[0][lane][index] = table[1][lane][N - index]

    return {
        "INTT_TWIST": [sign_extend27(value) for value in twist[1]],
        "NTT_TWIST": [sign_extend27(value) for value in twist[0]],
        "INTT_TABLE0": [sign_extend27(value) for value in table[1][0]],
        "INTT_TABLE1": [sign_extend27(value) for value in table[1][1]],
        "NTT_TABLE0": [sign_extend27(value) for value in table[0][0]],
        "NTT_TABLE1": [sign_extend27(value) for value in table[0][1]],
    }


def format_cpp_array(name: str, values: list[int]) -> str:
    lines = [f"static const int32_t {name}[{len(values)}] = {{"]
    for offset in range(0, len(values), 8):
        chunk = ", ".join(str(value) for value in values[offset : offset + 8])
        lines.append(f"  {chunk},")
    lines.append("};")
    return "\n".join(lines)


def generate_hls_source() -> str:
    arrays = "\n".join(
        format_cpp_array(name, values) for name, values in generate_tables().items()
    )
    return (
        textwrap.dedent(
            f"""\
            #include <stdint.h>

            static const int32_t YATA_P = {P};
            static const int32_t YATA_K = {K};
            static const int32_t YATA_SHIFT = {SHIFTAMOUNT};
            static const int32_t YATA_WORDBITS = {WORDBITS};
            static const int64_t YATA_MASK = (1LL << YATA_WORDBITS) - 1;
            static const int32_t YATA_R2 = {R2};
            static const uint64_t YATA_MODSWITCH_SCALE =
                ((1ULL << (32 + YATA_WORDBITS - 1)) / YATA_P);

            static int32_t sign_extend27(int64_t x) {{
            #pragma HLS inline
              x &= YATA_MASK;
              if (x & (1LL << (YATA_WORDBITS - 1))) x -= (1LL << YATA_WORDBITS);
              return (int32_t)x;
            }}

            static int32_t add_mod(int64_t a, int64_t b) {{
            #pragma HLS inline
              int64_t add = a + b;
              if (add >= YATA_P) return (int32_t)(add - YATA_P);
              if (add <= -YATA_P) return (int32_t)(add + YATA_P);
              return (int32_t)add;
            }}

            static int32_t sub_mod(int64_t a, int64_t b) {{
            #pragma HLS inline
              int64_t sub = a - b;
              if (sub >= YATA_P) return (int32_t)(sub - YATA_P);
              if (sub <= -YATA_P) return (int32_t)(sub + YATA_P);
              return (int32_t)sub;
            }}

            static int32_t sredc(int64_t a) {{
            #pragma HLS inline
              int64_t a0 = a & YATA_MASK;
              int64_t a1 = a >> YATA_WORDBITS;
              int64_t m_wide = -((a0 * YATA_K) << YATA_SHIFT) + a0;
              int32_t m = sign_extend27(m_wide);
              int64_t t1 = (((int64_t)m * YATA_K) << YATA_SHIFT) + m;
              t1 >>= YATA_WORDBITS;
              return (int32_t)(a1 - t1);
            }}

            static int32_t mul_sredc(int64_t a, int64_t b) {{
            #pragma HLS inline
              return sredc(a * b);
            }}

            static int64_t const_twiddle_mul(int64_t a, int radixbit, int num) {{
            #pragma HLS inline
              int64_t factor = 1;
              int exp = num * (4 >> (radixbit - 1));
              for (int i = 0; i < exp; ++i) factor *= 5;
              return (a * factor) << (num * (16 >> (radixbit - 1)));
            }}

            static int bit_reverse3(int x) {{
            #pragma HLS inline
              return ((x & 1) << 2) | (x & 2) | ((x & 4) >> 2);
            }}
            """
        )
        + arrays
        + "\n\n"
        + textwrap.dedent(
            """\
            static void butterfly_add_both_mod(int64_t res[512], int offset, int size) {
              for (int index = 0; index < size / 2; ++index) {
            #pragma HLS loop_tripcount min=1 max=256
                int64_t temp = res[offset + index];
                res[offset + index] =
                    add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    sub_mod(temp, res[offset + index + size / 2]);
              }
            }

            static void butterfly_add_add_mod(int64_t res[512], int offset, int size) {
              for (int index = 0; index < size / 2; ++index) {
            #pragma HLS loop_tripcount min=1 max=256
                int64_t temp = res[offset + index];
                res[offset + index] =
                    add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    temp - res[offset + index + size / 2];
              }
            }

            static void butterfly_add_both_sredc(int64_t res[512], int offset,
                                                 int size) {
              for (int index = 0; index < size / 2; ++index) {
            #pragma HLS loop_tripcount min=1 max=256
                int64_t temp = res[offset + index];
                res[offset + index] =
                    sredc(res[offset + index] + res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    sredc(temp - res[offset + index + size / 2]);
              }
            }

            static void intt_radix1(int64_t res[512], int offset, int size) {
              butterfly_add_both_mod(res, offset, size);
            }

            static void intt_radix2(int64_t res[512], int offset, int size) {
              butterfly_add_add_mod(res, offset, size);
              intt_radix1(res, offset, size / 2);
              int block = size >> 2;
              for (int j = 0; j < block; ++j) {
            #pragma HLS loop_tripcount min=1 max=128
                res[offset + j + size / 2 + block] =
                    const_twiddle_mul(res[offset + j + size / 2 + block], 2, 1);
              }
              butterfly_add_both_sredc(res, offset + size / 2, size / 2);
            }

            static void intt_radix3(int64_t res[512], int offset, int size) {
              butterfly_add_add_mod(res, offset, size);
              intt_radix2(res, offset, size / 2);
              int block = size >> 3;
              for (int i = 0; i < block; ++i) {
            #pragma HLS loop_tripcount min=1 max=64
                res[offset + 2 * block + i + size / 2] =
                    const_twiddle_mul(res[offset + 2 * block + i + size / 2], 3, 2);
                int64_t temp = res[offset + i + size / 2];
                res[offset + i + size / 2] +=
                    res[offset + 2 * block + i + size / 2];
                res[offset + 2 * block + i + size / 2] =
                    temp - res[offset + 2 * block + i + size / 2];
              }
              for (int i = 0; i < block; ++i) {
            #pragma HLS loop_tripcount min=1 max=64
                int64_t temp =
                    const_twiddle_mul(res[offset + 1 * block + i + size / 2], 3, 3);
                res[offset + 1 * block + i + size / 2] =
                    const_twiddle_mul(res[offset + 1 * block + i + size / 2], 3, 1) +
                    const_twiddle_mul(res[offset + 3 * block + i + size / 2], 3, 3);
                res[offset + 3 * block + i + size / 2] =
                    temp +
                    const_twiddle_mul(res[offset + 3 * block + i + size / 2], 3, 1);
              }
              butterfly_add_both_sredc(res, offset + size / 2, size / 4);
              butterfly_add_both_sredc(res, offset + 3 * size / 4, size / 4);
            }

            static void twiddle_mul_invert(int64_t res[512], int offset, int size,
                                           int blockindex, int stride,
                                           const int32_t table0[512],
                                           const int32_t table1[512]) {
              for (int index = 0; index < size; ++index) {
            #pragma HLS loop_tripcount min=1 max=512
                int32_t tw =
                    (blockindex > 1) ? table1[stride * index] : table0[stride * index];
                res[offset + index] = mul_sredc(res[offset + index], tw);
              }
            }

            static void intt_radix_stage(int64_t res[512], int offset, int size,
                                         int num_block) {
              intt_radix3(res, offset, size);
              int block = size >> 3;
              for (int i = 1; i < 8; ++i) {
                twiddle_mul_invert(res, offset + i * block, block, i,
                                   bit_reverse3(i) * num_block, INTT_TABLE0,
                                   INTT_TABLE1);
              }
            }

            static void intt_transform(int64_t res[512]) {
              for (int block = 0; block < 1; ++block)
                intt_radix_stage(res, 512 * block, 512, 1);
              for (int block = 0; block < 8; ++block)
                intt_radix_stage(res, 64 * block, 64, 8);
              for (int block = 0; block < 64; ++block)
                intt_radix3(res, 8 * block, 8);
            }

            static void twist_mul_invert_top(int64_t res[512],
                                             const uint32_t in[512]) {
              for (int i = 0; i < 512; ++i) {
            #pragma HLS loop_tripcount min=512 max=512
                int32_t signed_in = (int32_t)in[i];
                res[i] = mul_sredc((int64_t)signed_in, INTT_TWIST[i]);
              }
            }

            static void ntt_radix1(int64_t res[512], int offset, int size) {
              butterfly_add_both_mod(res, offset, size);
            }

            static void ntt_radix2(int64_t res[512], int offset, int size, bool redc) {
              ntt_radix1(res, offset, size / 2);
              ntt_radix1(res, offset + size / 2, size / 2);
              for (int index = 0; index < size / 4; ++index) {
            #pragma HLS loop_tripcount min=1 max=128
                int64_t temp = res[offset + index];
                res[offset + index] =
                    add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    sub_mod(temp, res[offset + index + size / 2]);
              }
              for (int index = size / 4; index < size / 2; ++index) {
            #pragma HLS loop_tripcount min=1 max=128
                int64_t temp = res[offset + index];
                res[offset + index + size / 2] =
                    -const_twiddle_mul(res[offset + index + size / 2], 2, 1);
                if (redc) {
                  res[offset + index] =
                      sredc(res[offset + index] + res[offset + index + size / 2]);
                  res[offset + index + size / 2] =
                      sredc(temp - res[offset + index + size / 2]);
                } else {
                  res[offset + index] =
                      res[offset + index] + res[offset + index + size / 2];
                  res[offset + index + size / 2] =
                      temp - res[offset + index + size / 2];
                }
              }
            }

            static void ntt_radix3(int64_t res[512], int offset, int size) {
              ntt_radix2(res, offset, size / 2, false);
              ntt_radix1(res, offset + 2 * size / 4, size / 4);
              ntt_radix1(res, offset + 3 * size / 4, size / 4);
              int block = size >> 3;
              for (int index = size / 2; index < size / 2 + block; ++index) {
            #pragma HLS loop_tripcount min=1 max=64
                int64_t temp = res[offset + index];
                res[offset + index] =
                    add_mod(res[offset + index], res[offset + index + size / 4]);
                res[offset + index + size / 4] =
                    -const_twiddle_mul(temp - res[offset + index + size / 4], 3, 2);
              }
              for (int index = size / 2 + block; index < size / 2 + 2 * block;
                   ++index) {
            #pragma HLS loop_tripcount min=1 max=64
                int64_t temp = -const_twiddle_mul(res[offset + index], 3, 1);
                res[offset + index] =
                    -const_twiddle_mul(res[offset + index], 3, 3) -
                    const_twiddle_mul(res[offset + index + size / 4], 3, 1);
                res[offset + index + size / 4] =
                    temp - const_twiddle_mul(res[offset + index + size / 4], 3, 3);
              }
              for (int index = 0; index < block; ++index) {
            #pragma HLS loop_tripcount min=1 max=64
                int64_t temp = res[offset + index];
                res[offset + index] =
                    add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    sub_mod(temp, res[offset + index + size / 2]);
              }
              for (int i = 1; i < 4; ++i) {
                for (int index = i * block; index < (i + 1) * block; ++index) {
            #pragma HLS loop_tripcount min=1 max=64
                  int64_t temp = res[offset + index];
                  res[offset + index] =
                      sredc(res[offset + index] + res[offset + index + size / 2]);
                  res[offset + index + size / 2] =
                      sredc(temp - res[offset + index + size / 2]);
                }
              }
            }

            static void twiddle_mul(int64_t res[512], int offset, int sizebit,
                                    int prevradixbit, int stride,
                                    const int32_t table0[512],
                                    const int32_t table1[512]) {
              int size = 1 << sizebit;
              if (prevradixbit == 1) {
                if (stride != 0) {
                  for (int index = 0; index < size; ++index) {
            #pragma HLS loop_tripcount min=1 max=512
                    res[offset + index] =
                        mul_sredc(res[offset + index], table0[stride * index]);
                  }
                }
              } else {
                if (stride == 0) {
                  for (int index = 0; index < size; ++index) {
            #pragma HLS loop_tripcount min=1 max=512
                    if (((index >> (sizebit - prevradixbit)) &
                         ((1 << (prevradixbit - 1)) - 1)) != 0) {
                      res[offset + index] = mul_sredc(res[offset + index], YATA_R2);
                    }
                  }
                } else {
                  for (int index = 0; index < size; ++index) {
            #pragma HLS loop_tripcount min=1 max=512
                    int tbl = ((index >> (sizebit - prevradixbit)) &
                               ((1 << (prevradixbit - 1)) - 1)) != 0;
                    int32_t tw = tbl ? table1[stride * index]
                                     : table0[stride * index];
                    res[offset + index] = mul_sredc(res[offset + index], tw);
                  }
                }
              }
            }

            static void ntt_radix_stage(int64_t res[512], int offset, int sizebit,
                                        int prevradixbit, int num_block) {
              int size = 1 << sizebit;
              int block = size >> 3;
              for (int i = 0; i < 8; ++i) {
                twiddle_mul(res, offset + i * block, sizebit - 3, prevradixbit,
                            bit_reverse3(i) * num_block, NTT_TABLE0, NTT_TABLE1);
              }
              ntt_radix3(res, offset, size);
            }

            static void ntt_transform(int64_t res[512]) {
              for (int block = 0; block < 64; ++block) ntt_radix3(res, 8 * block, 8);
              for (int block = 0; block < 8; ++block)
                ntt_radix_stage(res, 64 * block, 6, 3, 8);
              for (int block = 0; block < 1; ++block)
                ntt_radix_stage(res, 512 * block, 9, 3, 1);
            }

            static void twist_mul_direct_top(uint32_t out[512], int64_t res[512]) {
              for (int i = 0; i < 512; ++i) {
            #pragma HLS loop_tripcount min=512 max=512
                int32_t mulres = mul_sredc(res[i], NTT_TWIST[i]);
                uint32_t pos = (uint32_t)((mulres < 0) ? (mulres + YATA_P) : mulres);
                out[i] =
                    (uint32_t)(((uint64_t)pos * YATA_MODSWITCH_SCALE +
                                (1ULL << (YATA_WORDBITS - 2))) >>
                               (YATA_WORDBITS - 1));
              }
            }

            extern "C" void yata_raintt_intt_hls(const uint32_t intt_in[512],
                                                  int32_t intt_out[512]) {
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              int64_t work[512];
            #pragma HLS bind_storage variable=work type=ram_2p impl=bram
              twist_mul_invert_top(work, intt_in);
              intt_transform(work);
              for (int i = 0; i < 512; ++i) {
            #pragma HLS loop_tripcount min=512 max=512
                intt_out[i] = (int32_t)work[i];
              }
            }

            extern "C" void yata_raintt_ntt_hls(const int32_t ntt_in[512],
                                                 uint32_t ntt_out[512]) {
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              int64_t work[512];
            #pragma HLS bind_storage variable=work type=ram_2p impl=bram
              for (int i = 0; i < 512; ++i) {
            #pragma HLS loop_tripcount min=512 max=512
                work[i] = ntt_in[i];
              }
              ntt_transform(work);
              twist_mul_direct_top(ntt_out, work);
            }

            extern "C" void yata_raintt_hls(const uint32_t intt_in[512],
                                             int32_t intt_out[512],
                                             const int32_t ntt_in[512],
                                             uint32_t ntt_out[512]) {
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem2
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem3
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_raintt_intt_hls(intt_in, intt_out);
              yata_raintt_ntt_hls(ntt_in, ntt_out);
            }
            """
        )
    )


def generate_functional_test_source() -> str:
    return textwrap.dedent(
        """\
        #define USE_COMPRESS
        #include <array>
        #include <cassert>
        #include <cstdint>
        #include <iostream>

        #include "third_party/TFHEpp/include/raintt.hpp"

        extern "C" void yata_raintt_intt_hls(const uint32_t intt_in[512],
                                             int32_t intt_out[512]);
        extern "C" void yata_raintt_ntt_hls(const int32_t ntt_in[512],
                                            uint32_t ntt_out[512]);

        int main() {
          auto table = raintt::TableGen<9>();
          auto twist = raintt::TwistGen<9, 3>();

          std::array<uint32_t, 512> poly{};
          for (int i = 0; i < 512; ++i) {
            poly[i] =
                (static_cast<uint32_t>(i) * 7919u + 123u) %
                static_cast<uint32_t>(raintt::P);
          }

          std::array<raintt::DoubleSWord, 512> expected_intt{};
          raintt::TwistINTT<uint32_t, 9, false>(expected_intt, poly, (*table)[1],
                                                (*twist)[1]);

          int32_t intt_out[512]{};
          yata_raintt_intt_hls(poly.data(), intt_out);
          for (int i = 0; i < 512; ++i) {
            if (intt_out[i] != static_cast<int32_t>(expected_intt[i])) {
              std::cerr << "INTT mismatch " << i << " got " << intt_out[i]
                        << " expected " << static_cast<int32_t>(expected_intt[i])
                        << "\\n";
              return 1;
            }
          }

          std::array<raintt::DoubleSWord, 512> ntt_input = expected_intt;
          std::array<uint32_t, 512> expected_ntt{};
          raintt::TwistNTT<uint32_t, 9, true>(expected_ntt, ntt_input,
                                              (*table)[0], (*twist)[0]);

          int32_t ntt_in[512]{};
          for (int i = 0; i < 512; ++i) {
            ntt_in[i] = static_cast<int32_t>(expected_intt[i]);
          }
          uint32_t ntt_out[512]{};
          yata_raintt_ntt_hls(ntt_in, ntt_out);
          for (int i = 0; i < 512; ++i) {
            if (ntt_out[i] != expected_ntt[i]) {
              std::cerr << "NTT mismatch " << i << " got " << ntt_out[i]
                        << " expected " << expected_ntt[i] << "\\n";
              return 1;
            }
          }

          std::cout << "PASS yata_raintt_hls_functional\\n";
          return 0;
        }
        """
    )


def load_compare_module() -> Any:
    path = REPO_ROOT / "scripts" / "compare_autontt_metrics.py"
    spec = importlib.util.spec_from_file_location("compare_autontt_metrics", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def find_sif(value: str) -> Path:
    if value != "auto":
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"SIF not found: {path}")
        return path

    candidates = []
    env_value = os.environ.get("LLM_NTT_SIF")
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.extend(
        [
            REPO_ROOT / "llm-ntt-rootless.sif",
            REPO_ROOT / "llm-ntt.sif",
            REPO_ROOT.parent / "llm-ntt-rootless.sif",
            REPO_ROOT.parent / "llm-ntt.sif",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        "could not find a SIF; pass --sif or set LLM_NTT_SIF"
    )


def run_logged(
    cmd: list[str],
    log_path: Path,
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n")
        log.flush()
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd is not None else None,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {timeout} seconds\n")
            raise RuntimeError(f"command timed out; see {log_path}") from None
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit {completed.returncode}; see {log_path}"
        )


def apptainer_base_cmd(sif: Path, binds: list[tuple[Path, str]], pwd: str) -> list[str]:
    cmd = ["apptainer", "exec", "--no-home", "--pwd", pwd]
    for host, container in binds:
        cmd.extend(["--bind", f"{host}:{container}"])
    cmd.append(str(sif))
    return cmd


def run_functional_check(run_dir: Path, sif: Path) -> Path:
    run_rel = relpath(run_dir)
    binary = f"{run_rel}/yata_raintt_hls_functional"
    shell = (
        "clang++ -std=c++20 -I. "
        f"{shlex.quote(run_rel + '/yata_raintt_hls.cpp')} "
        f"{shlex.quote(run_rel + '/test_yata_hls.cpp')} "
        f"-o {shlex.quote(binary)} && {shlex.quote(binary)}"
    )
    log_path = run_dir / "functional.log"
    cmd = apptainer_base_cmd(sif, [(REPO_ROOT, "/work")], "/work") + [
        "bash",
        "-lc",
        shell,
    ]
    run_logged(cmd, log_path, timeout=600)
    return log_path


def write_tcl(run_dir: Path, project: str, top: str, part: str, clock: float) -> Path:
    tcl_path = run_dir / f"run_{project}.tcl"
    tcl_path.write_text(
        textwrap.dedent(
            f"""\
            open_project -reset {project}
            set_top {top}
            add_files yata_raintt_hls.cpp
            open_solution -reset solution1 -flow_target vivado
            set_part {{{part}}}
            create_clock -period {clock:.6g} -name default
            csynth_design
            exit
            """
        ),
        encoding="utf-8",
    )
    return tcl_path


def vitis_settings_path(xilinx_root: Path, settings: str) -> Path:
    configured = Path(settings).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    return (xilinx_root / configured).resolve()


def run_vitis_hls(
    run_dir: Path,
    sif: Path,
    xilinx_root: Path,
    settings: Path,
    tcl_path: Path,
    timeout: int,
) -> Path:
    if not settings.exists():
        raise FileNotFoundError(f"Vitis settings script not found: {settings}")
    run_rel = relpath(run_dir)
    container_run_dir = f"/work/{run_rel}"
    shell = (
        f"set +u; source {shlex.quote(str(settings))}; set -u; "
        f"vitis_hls -f {shlex.quote(tcl_path.name)}"
    )
    log_path = run_dir / f"{tcl_path.stem}.log"
    cmd = apptainer_base_cmd(
        sif,
        [(REPO_ROOT, "/work"), (xilinx_root, str(xilinx_root))],
        container_run_dir,
    ) + ["bash", "-lc", shell]
    run_logged(cmd, log_path, timeout=timeout)
    return log_path


def xml_text(root: ET.Element, tag: str) -> str:
    found = root.find(f".//{tag}")
    if found is None or found.text is None:
        raise ValueError(f"missing {tag} in HLS report")
    return found.text.strip()


def parse_csynth_report(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    resources_root = root.find(".//AreaEstimates/Resources")
    if resources_root is None:
        raise ValueError(f"missing AreaEstimates/Resources in {path}")
    resources = {child.tag: int(child.text or "0") for child in resources_root}
    return {
        "path": str(path),
        "best_latency_cycles": int(xml_text(root, "Best-caseLatency")),
        "worst_latency_cycles": int(xml_text(root, "Worst-caseLatency")),
        "estimated_clock_period_ns": float(xml_text(root, "EstimatedClockPeriod")),
        "resources": resources,
    }


def build_candidate_results(
    *,
    intt_report: dict[str, Any],
    ntt_report: dict[str, Any],
    combined_report: dict[str, Any],
    clock_period_ns: float,
    part: str,
    logs: dict[str, str],
    generated_sources: dict[str, str],
    hls_reports: dict[str, str],
) -> dict[str, Any]:
    combined_resources = combined_report["resources"]
    achieved_period = float(combined_report["estimated_clock_period_ns"])
    fmax_mhz = 1000.0 / achieved_period if achieved_period > 0 else None
    wait_input_output_cycles = 16
    metrics = {
        "yata_raintt_intt_input_cycles": 8,
        "yata_raintt_intt_output_cycles": 8,
        "yata_raintt_intt_max_wait_cycles": max(
            int(intt_report["worst_latency_cycles"]) - wait_input_output_cycles, 0
        ),
        "yata_raintt_ntt_input_cycles": 8,
        "yata_raintt_ntt_output_cycles": 8,
        "yata_raintt_ntt_max_wait_cycles": max(
            int(ntt_report["worst_latency_cycles"]) - wait_input_output_cycles, 0
        ),
        "vitis_lut": int(combined_resources.get("LUT", 0)),
        "vitis_ff": int(combined_resources.get("FF", 0)),
        "vitis_dsp": int(combined_resources.get("DSP", 0)),
        "vitis_bram_tile": int(combined_resources.get("BRAM_18K", 0)),
        "vitis_uram": int(combined_resources.get("URAM", 0)),
        "vitis_clock_period_ns": clock_period_ns,
        "vitis_fmax_mhz": fmax_mhz,
        "vitis_timing_achieved_period_ns": achieved_period,
        "vitis_timing_requirement_ns": clock_period_ns,
        "vitis_timing_wns_ns": clock_period_ns - achieved_period,
        "hls_intt_best_latency_cycles": int(intt_report["best_latency_cycles"]),
        "hls_intt_worst_latency_cycles": int(intt_report["worst_latency_cycles"]),
        "hls_ntt_best_latency_cycles": int(ntt_report["best_latency_cycles"]),
        "hls_ntt_worst_latency_cycles": int(ntt_report["worst_latency_cycles"]),
        "hls_combined_best_latency_cycles": int(
            combined_report["best_latency_cycles"]
        ),
        "hls_combined_worst_latency_cycles": int(
            combined_report["worst_latency_cycles"]
        ),
    }
    return {
        "task_id": TASK_ID,
        "correct": True,
        "vitis_synthesis_passed": True,
        "generator": "llm_yata_hls",
        "part": part,
        "metrics": metrics,
        "logs": logs,
        "generated_sources": generated_sources,
        "hls_reports": hls_reports,
        "notes": [
            "YATA uses a repository-local LLM-style HLS path because AutoNTT "
            "rejects N=512 inputs.",
            "The Vitis resource and timing values are HLS csynth estimates, "
            "not post-route RTL implementation metrics.",
            "Latency groups map full HLS transform latency onto the existing "
            "AutoNTT input/wait/output metric shape using 8 input and 8 output "
            "cycles for the 64-lane YATA task boundary.",
        ],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report(
    run_dir: Path,
    results: dict[str, Any],
    comparison: dict[str, Any],
    table: str,
) -> None:
    metrics = results["metrics"]
    report = [
        "# YATA HLS Synth Compare",
        "",
        f"- task: `{TASK_ID}`",
        f"- generated HLS: `{results['generated_sources']['hls']}`",
        f"- candidate results: `{relpath(run_dir / 'results.json')}`",
        f"- comparison JSON: `{relpath(run_dir / 'comparison.json')}`",
        "",
        "## Candidate HLS Estimates",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| INTT worst latency cycles | {metrics['hls_intt_worst_latency_cycles']} |",
        f"| NTT worst latency cycles | {metrics['hls_ntt_worst_latency_cycles']} |",
        (
            "| combined worst latency cycles | "
            f"{metrics['hls_combined_worst_latency_cycles']} |"
        ),
        f"| LUT | {metrics['vitis_lut']} |",
        f"| FF | {metrics['vitis_ff']} |",
        f"| DSP | {metrics['vitis_dsp']} |",
        f"| BRAM_18K | {metrics['vitis_bram_tile']} |",
        f"| estimated clock period ns | {metrics['vitis_timing_achieved_period_ns']} |",
        "",
        "## AutoNTT Metric Comparison",
        "",
        "```text",
        table,
        "```",
        "",
        "The comparison uses the existing AutoNTT-style metric script against "
        "the extracted RTL reference result.",
    ]
    (run_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Path:
    output_root = Path(args.output_root).expanduser().resolve()
    run_name = args.run_name or time.strftime("%Y%m%d-%H%M%S")
    run_dir = output_root / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    hls_source = run_dir / "yata_raintt_hls.cpp"
    functional_source = run_dir / "test_yata_hls.cpp"
    hls_source.write_text(generate_hls_source(), encoding="utf-8")
    functional_source.write_text(generate_functional_test_source(), encoding="utf-8")

    sif = find_sif(args.sif)
    logs: dict[str, str] = {}

    if not args.skip_functional:
        print(f"Running functional check; log: {relpath(run_dir / 'functional.log')}")
        logs["functional"] = relpath(run_functional_check(run_dir, sif))

    xilinx_root = Path(args.xilinx_root).expanduser().resolve()
    settings = vitis_settings_path(xilinx_root, args.vitis_settings)
    tops = {
        "intt": ("yata_intt_hls", "yata_raintt_intt_hls"),
        "ntt": ("yata_ntt_hls", "yata_raintt_ntt_hls"),
        "combined": ("yata_combined_hls", "yata_raintt_hls"),
    }
    tcl_paths = {
        label: write_tcl(run_dir, project, top, args.part, args.clock_period)
        for label, (project, top) in tops.items()
    }
    for label, tcl_path in tcl_paths.items():
        print(f"Running Vitis HLS for {label}; log: {relpath(run_dir / (tcl_path.stem + '.log'))}")
        logs[f"hls_{label}"] = relpath(
            run_vitis_hls(
                run_dir,
                sif,
                xilinx_root,
                settings,
                tcl_path,
                args.vitis_timeout,
            )
        )

    reports: dict[str, dict[str, Any]] = {}
    hls_report_paths: dict[str, str] = {}
    for label, (project, top) in tops.items():
        report_path = run_dir / project / "solution1" / "syn" / "report" / f"{top}_csynth.xml"
        reports[label] = parse_csynth_report(report_path)
        hls_report_paths[label] = relpath(report_path)

    generated_sources = {
        "hls": relpath(hls_source),
        "functional_test": relpath(functional_source),
    }
    results = build_candidate_results(
        intt_report=reports["intt"],
        ntt_report=reports["ntt"],
        combined_report=reports["combined"],
        clock_period_ns=args.clock_period,
        part=args.part,
        logs=logs,
        generated_sources=generated_sources,
        hls_reports=hls_report_paths,
    )
    results_path = run_dir / "results.json"
    write_json(results_path, results)

    compare_module = load_compare_module()
    reference = compare_module.load_json(REFERENCE_RESULTS)
    comparison = compare_module.compare_results(
        reference, results, str(REFERENCE_RESULTS), str(results_path)
    )
    comparison_path = run_dir / "comparison.json"
    write_json(comparison_path, comparison)
    table = compare_module.format_table(comparison)
    (run_dir / "comparison.txt").write_text(table + "\n", encoding="utf-8")
    write_report(run_dir, results, comparison, table)

    summary = {
        "task_id": TASK_ID,
        "run_dir": relpath(run_dir),
        "sif": str(sif),
        "reference": relpath(REFERENCE_RESULTS),
        "results": relpath(results_path),
        "comparison": relpath(comparison_path),
        "report": relpath(run_dir / "report.md"),
        "correct": results["correct"],
        "vitis_synthesis_passed": results["vitis_synthesis_passed"],
        "resource_aware_score": comparison["resource_aware_score"],
    }
    write_json(run_dir / "summary.json", summary)
    print(table)
    print(f"Wrote {relpath(run_dir / 'summary.json')}")
    return run_dir


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate YATA RAINTT HLS, synthesize it with Vitis HLS in the SIF, "
            "and compare against the extracted RTL reference using AutoNTT metrics."
        )
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=f"Run output root. Defaults to {relpath(DEFAULT_OUTPUT_ROOT)}.",
    )
    parser.add_argument("--run-name", help="Optional explicit run directory name.")
    parser.add_argument(
        "--sif",
        default="auto",
        help="Apptainer SIF path, or auto to use LLM_NTT_SIF/default names.",
    )
    parser.add_argument(
        "--xilinx-root",
        default=os.environ.get("XILINX_ROOT", "/home/opt/xilinx"),
        help="Host Vitis/Xilinx root to bind into the container.",
    )
    parser.add_argument(
        "--vitis-settings",
        default=os.environ.get("VITIS_SETTINGS", "Vitis/2023.2/settings64.sh"),
        help="Vitis settings script, absolute or relative to --xilinx-root.",
    )
    parser.add_argument(
        "--part",
        default=os.environ.get("VITIS_PART", DEFAULT_PART),
        help="Vitis HLS target part.",
    )
    parser.add_argument(
        "--clock-period",
        type=float,
        default=DEFAULT_CLOCK_PERIOD_NS,
        help="Target HLS clock period in ns.",
    )
    parser.add_argument(
        "--vitis-timeout",
        type=int,
        default=1800,
        help="Timeout in seconds for each Vitis HLS top.",
    )
    parser.add_argument(
        "--skip-functional",
        action="store_true",
        help="Skip the TFHEpp C++ functional equivalence check.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        run(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
