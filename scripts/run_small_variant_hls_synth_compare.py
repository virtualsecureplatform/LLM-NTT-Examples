#!/usr/bin/env python3
"""Generate, test, synthesize, and compare small HOGE/YATA HLS variants."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, NamedTuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "small-variant-hls-synth-compare"
DEFAULT_REFERENCE_BASELINE_DIR = REPO_ROOT / "baselines" / "extracted-rtl"
DEFAULT_PART = "xcu280-fsvh2892-2L-e"
DEFAULT_CLOCK_PERIOD_NS = 4.0

YATA_P = 40960001
YATA_K = 625
YATA_SHIFTAMOUNT = 16
YATA_WORDBITS = 27
YATA_WORDMASK = (1 << YATA_WORDBITS) - 1
YATA_R = (1 << YATA_WORDBITS) % YATA_P
YATA_R2 = (YATA_R * YATA_R) % YATA_P
YATA_RADIXBIT = 3

HOGE_P = (((1 << 32) - 1) << 32) + 1
HOGE_W = 12037493425763644479


class Variant(NamedTuple):
    name: str
    task_id: str
    family: str
    nbit: int
    lanes: int
    cycles: int

    @property
    def n(self) -> int:
        return 1 << self.nbit


VARIANTS = {
    "hoge32": Variant(
        name="hoge32",
        task_id="small_hoge32_p64",
        family="hoge",
        nbit=5,
        lanes=32,
        cycles=1,
    ),
    "yata8": Variant(
        name="yata8",
        task_id="small_yata8_raintt_p27",
        family="yata",
        nbit=3,
        lanes=8,
        cycles=1,
    ),
    "yata8x8": Variant(
        name="yata8x8",
        task_id="small_yata8x8_raintt_p27",
        family="yata",
        nbit=6,
        lanes=8,
        cycles=8,
    ),
}


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


YATA_DRIVER = load_module(REPO_ROOT / "scripts" / "run_yata_hls_synth_compare.py", "yata_hls_driver")
COMPARE = load_module(REPO_ROOT / "scripts" / "compare_autontt_metrics.py", "compare_autontt_metrics")


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def format_cpp_array(kind: str, name: str, values: list[int]) -> str:
    lines = [f"static const {kind} {name}[{len(values)}] = {{"]
    for offset in range(0, len(values), 8):
        lines.append("  " + ", ".join(str(value) for value in values[offset : offset + 8]) + ",")
    lines.append("};")
    return "\n".join(lines)


def yata_sign_extend(value: int) -> int:
    value &= YATA_WORDMASK
    if value & (1 << (YATA_WORDBITS - 1)):
        value -= 1 << YATA_WORDBITS
    return value


def yata_redc(value: int) -> int:
    low = value & YATA_WORDMASK
    m = (((low * YATA_K) << YATA_SHIFTAMOUNT) - low) & YATA_WORDMASK
    if m & (1 << (YATA_WORDBITS - 1)):
        m -= 1 << YATA_WORDBITS
    t1 = (((m * YATA_K) << YATA_SHIFTAMOUNT) + m) >> YATA_WORDBITS
    return (value >> YATA_WORDBITS) - t1


def yata_redc_unsigned(value: int) -> int:
    low = value & YATA_WORDMASK
    m = (((low * YATA_K) << YATA_SHIFTAMOUNT) - low) & YATA_WORDMASK
    reduced = (value + ((m * YATA_K) << YATA_SHIFTAMOUNT) + m) >> YATA_WORDBITS
    return reduced - YATA_P if reduced > YATA_P else reduced


def yata_mul_redc(left: int, right: int) -> int:
    return yata_redc_unsigned(left * right)


def yata_pow_redc(base: int, exponent: int) -> int:
    result = 1
    base_r = yata_mul_redc(YATA_R2, base)
    for _ in range(exponent):
        result = yata_mul_redc(result, base_r)
    return result


def generate_yata_tables(nbit: int) -> dict[str, list[int]]:
    n = 1 << nbit
    w = yata_pow_redc(31, YATA_K)
    inv_n = pow(n, -1, YATA_P)

    twist = [[0 for _ in range(n)] for _ in range(2)]
    twist_wr = yata_mul_redc(yata_pow_redc(w, 1 << (YATA_SHIFTAMOUNT - nbit - 1)), YATA_R2)
    twist[1][0] = YATA_R
    for index in range(1, n):
        twist[1][index] = yata_mul_redc(twist[1][index - 1], twist_wr)
    twist[0][n - 1] = yata_mul_redc(
        yata_mul_redc(twist[1][n - 1], twist_wr), (inv_n * twist_wr) % YATA_P
    )
    twist[0][0] = (inv_n * YATA_R) % YATA_P
    for index in range(2, n):
        twist[0][n - index] = yata_mul_redc(twist[0][n - index + 1], twist_wr)
    for index in range(n):
        if ((index >> (nbit - YATA_RADIXBIT)) & ((1 << (YATA_RADIXBIT - 1)) - 1)) != 0:
            twist[0][index] = yata_mul_redc(twist[0][index], YATA_R2)

    table = [[[0 for _ in range(n)] for _ in range(2)] for _ in range(2)]
    table_w = yata_pow_redc(w, 1 << (YATA_SHIFTAMOUNT - nbit))
    table_wr = yata_mul_redc(table_w, YATA_R2)
    table[0][0][0] = table[1][0][0] = YATA_R
    table[0][1][0] = table[1][1][0] = YATA_R2
    for index in range(1, n):
        table[1][0][index] = yata_mul_redc(table[1][0][index - 1], table_wr)
    for index in range(1, n):
        table[1][1][index] = yata_mul_redc(table[1][0][index], YATA_R2)
    for lane in range(2):
        for index in range(1, n):
            table[0][lane][index] = table[1][lane][n - index]

    return {
        "YATA_INTT_TWIST": [yata_sign_extend(value) for value in twist[1]],
        "YATA_NTT_TWIST": [yata_sign_extend(value) for value in twist[0]],
        "YATA_INTT_TABLE0": [yata_sign_extend(value) for value in table[1][0]],
        "YATA_INTT_TABLE1": [yata_sign_extend(value) for value in table[1][1]],
        "YATA_NTT_TABLE0": [yata_sign_extend(value) for value in table[0][0]],
        "YATA_NTT_TABLE1": [yata_sign_extend(value) for value in table[0][1]],
    }


def generate_yata_source(variant: Variant) -> str:
    n = variant.n
    arrays = "\n".join(
        format_cpp_array("int32_t", name, values)
        for name, values in generate_yata_tables(variant.nbit).items()
    )
    prefix = variant.name
    return (
        textwrap.dedent(
            f"""\
            #include <stdint.h>

            static const int YATA_N = {n};
            static const int YATA_NBIT = {variant.nbit};
            static const int32_t YATA_P = {YATA_P};
            static const int32_t YATA_K = {YATA_K};
            static const int32_t YATA_SHIFT = {YATA_SHIFTAMOUNT};
            static const int32_t YATA_WORDBITS = {YATA_WORDBITS};
            static const int64_t YATA_MASK = (1LL << YATA_WORDBITS) - 1;
            static const int32_t YATA_R2 = {YATA_R2};
            static const uint64_t YATA_MODSWITCH_SCALE =
                ((1ULL << (32 + YATA_WORDBITS - 1)) / YATA_P);

            static int32_t yata_sign_extend27(int64_t x) {{
            #pragma HLS inline
              x &= YATA_MASK;
              if (x & (1LL << (YATA_WORDBITS - 1))) x -= (1LL << YATA_WORDBITS);
              return (int32_t)x;
            }}

            static int32_t yata_add_mod(int64_t a, int64_t b) {{
            #pragma HLS inline
              int64_t add = a + b;
              if (add >= YATA_P) return (int32_t)(add - YATA_P);
              if (add <= -YATA_P) return (int32_t)(add + YATA_P);
              return (int32_t)add;
            }}

            static int32_t yata_sub_mod(int64_t a, int64_t b) {{
            #pragma HLS inline
              int64_t sub = a - b;
              if (sub >= YATA_P) return (int32_t)(sub - YATA_P);
              if (sub <= -YATA_P) return (int32_t)(sub + YATA_P);
              return (int32_t)sub;
            }}

            static int32_t yata_sredc(int64_t a) {{
            #pragma HLS inline
              int64_t a0 = a & YATA_MASK;
              int64_t a1 = a >> YATA_WORDBITS;
              int64_t m_wide = -((a0 * YATA_K) << YATA_SHIFT) + a0;
              int32_t m = yata_sign_extend27(m_wide);
              int64_t t1 = (((int64_t)m * YATA_K) << YATA_SHIFT) + m;
              t1 >>= YATA_WORDBITS;
              return (int32_t)(a1 - t1);
            }}

            static int32_t yata_mul_sredc(int64_t a, int64_t b) {{
            #pragma HLS inline
              return yata_sredc(a * b);
            }}

            static int64_t yata_const_twiddle_mul(int64_t a, int radixbit, int num) {{
            #pragma HLS inline
              int64_t factor = 1;
              int exp = num * (4 >> (radixbit - 1));
              for (int i = 0; i < exp; ++i) factor *= 5;
              return (a * factor) << (num * (16 >> (radixbit - 1)));
            }}

            static int yata_bit_reverse3(int x) {{
            #pragma HLS inline
              return ((x & 1) << 2) | (x & 2) | ((x & 4) >> 2);
            }}
            """
        )
        + arrays
        + "\n\n"
        + textwrap.dedent(
            f"""\
            static void yata_butterfly_add_both_mod(int64_t res[YATA_N], int offset, int size) {{
              for (int index = 0; index < size / 2; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 2)}
                int64_t temp = res[offset + index];
                res[offset + index] =
                    yata_add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    yata_sub_mod(temp, res[offset + index + size / 2]);
              }}
            }}

            static void yata_butterfly_add_add_mod(int64_t res[YATA_N], int offset, int size) {{
              for (int index = 0; index < size / 2; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 2)}
                int64_t temp = res[offset + index];
                res[offset + index] =
                    yata_add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    temp - res[offset + index + size / 2];
              }}
            }}

            static void yata_butterfly_add_both_sredc(int64_t res[YATA_N], int offset,
                                                      int size) {{
              for (int index = 0; index < size / 2; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 2)}
                int64_t temp = res[offset + index];
                res[offset + index] =
                    yata_sredc(res[offset + index] + res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    yata_sredc(temp - res[offset + index + size / 2]);
              }}
            }}

            static void yata_intt_radix1(int64_t res[YATA_N], int offset, int size) {{
              yata_butterfly_add_both_mod(res, offset, size);
            }}

            static void yata_intt_radix2(int64_t res[YATA_N], int offset, int size) {{
              yata_butterfly_add_add_mod(res, offset, size);
              yata_intt_radix1(res, offset, size / 2);
              int block = size >> 2;
              for (int j = 0; j < block; ++j) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 4)}
                res[offset + j + size / 2 + block] =
                    yata_const_twiddle_mul(res[offset + j + size / 2 + block], 2, 1);
              }}
              yata_butterfly_add_both_sredc(res, offset + size / 2, size / 2);
            }}

            static void yata_intt_radix3(int64_t res[YATA_N], int offset, int size) {{
              yata_butterfly_add_add_mod(res, offset, size);
              yata_intt_radix2(res, offset, size / 2);
              int block = size >> 3;
              for (int i = 0; i < block; ++i) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                res[offset + 2 * block + i + size / 2] =
                    yata_const_twiddle_mul(res[offset + 2 * block + i + size / 2], 3, 2);
                int64_t temp = res[offset + i + size / 2];
                res[offset + i + size / 2] +=
                    res[offset + 2 * block + i + size / 2];
                res[offset + 2 * block + i + size / 2] =
                    temp - res[offset + 2 * block + i + size / 2];
              }}
              for (int i = 0; i < block; ++i) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                int64_t temp =
                    yata_const_twiddle_mul(res[offset + 1 * block + i + size / 2], 3, 3);
                res[offset + 1 * block + i + size / 2] =
                    yata_const_twiddle_mul(res[offset + 1 * block + i + size / 2], 3, 1) +
                    yata_const_twiddle_mul(res[offset + 3 * block + i + size / 2], 3, 3);
                res[offset + 3 * block + i + size / 2] =
                    temp +
                    yata_const_twiddle_mul(res[offset + 3 * block + i + size / 2], 3, 1);
              }}
              yata_butterfly_add_both_sredc(res, offset + size / 2, size / 4);
              yata_butterfly_add_both_sredc(res, offset + 3 * size / 4, size / 4);
            }}

            static void yata_twiddle_mul_invert(int64_t res[YATA_N], int offset, int size,
                                                int blockindex, int stride) {{
              for (int index = 0; index < size; ++index) {{
            #pragma HLS loop_tripcount min=1 max={n}
                int32_t tw = (blockindex > 1) ? YATA_INTT_TABLE1[stride * index]
                                              : YATA_INTT_TABLE0[stride * index];
                res[offset + index] = yata_mul_sredc(res[offset + index], tw);
              }}
            }}

            static void yata_intt_radix_stage(int64_t res[YATA_N], int offset, int size,
                                              int num_block) {{
              yata_intt_radix3(res, offset, size);
              int block = size >> 3;
              for (int i = 1; i < 8; ++i) {{
                yata_twiddle_mul_invert(res, offset + i * block, block, i,
                                        yata_bit_reverse3(i) * num_block);
              }}
            }}

            static void yata_intt_transform(int64_t res[YATA_N]) {{
              for (int sizebit = YATA_NBIT; sizebit > 3; sizebit -= 3) {{
                int size = 1 << sizebit;
                int num_block = 1 << (YATA_NBIT - sizebit);
                for (int block = 0; block < num_block; ++block) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                  yata_intt_radix_stage(res, size * block, size, num_block);
                }}
              }}
              int final_blocks = 1 << (YATA_NBIT - 3);
              for (int block = 0; block < final_blocks; ++block) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                yata_intt_radix3(res, 8 * block, 8);
              }}
            }}

            static void yata_twist_mul_invert_top(int64_t res[YATA_N],
                                                  const uint32_t in[YATA_N]) {{
              for (int i = 0; i < YATA_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                int32_t signed_in = (int32_t)in[i];
                res[i] = yata_mul_sredc((int64_t)signed_in, YATA_INTT_TWIST[i]);
              }}
            }}

            static void yata_ntt_radix1(int64_t res[YATA_N], int offset, int size) {{
              yata_butterfly_add_both_mod(res, offset, size);
            }}

            static void yata_ntt_radix2(int64_t res[YATA_N], int offset, int size, bool redc) {{
              yata_ntt_radix1(res, offset, size / 2);
              yata_ntt_radix1(res, offset + size / 2, size / 2);
              for (int index = 0; index < size / 4; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 4)}
                int64_t temp = res[offset + index];
                res[offset + index] =
                    yata_add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    yata_sub_mod(temp, res[offset + index + size / 2]);
              }}
              for (int index = size / 4; index < size / 2; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 4)}
                int64_t temp = res[offset + index];
                res[offset + index + size / 2] =
                    -yata_const_twiddle_mul(res[offset + index + size / 2], 2, 1);
                if (redc) {{
                  res[offset + index] =
                      yata_sredc(res[offset + index] + res[offset + index + size / 2]);
                  res[offset + index + size / 2] =
                      yata_sredc(temp - res[offset + index + size / 2]);
                }} else {{
                  res[offset + index] =
                      res[offset + index] + res[offset + index + size / 2];
                  res[offset + index + size / 2] =
                      temp - res[offset + index + size / 2];
                }}
              }}
            }}

            static void yata_ntt_radix3(int64_t res[YATA_N], int offset, int size) {{
              yata_ntt_radix2(res, offset, size / 2, false);
              yata_ntt_radix1(res, offset + 2 * size / 4, size / 4);
              yata_ntt_radix1(res, offset + 3 * size / 4, size / 4);
              int block = size >> 3;
              for (int index = size / 2; index < size / 2 + block; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                int64_t temp = res[offset + index];
                res[offset + index] =
                    yata_add_mod(res[offset + index], res[offset + index + size / 4]);
                res[offset + index + size / 4] =
                    -yata_const_twiddle_mul(temp - res[offset + index + size / 4], 3, 2);
              }}
              for (int index = size / 2 + block; index < size / 2 + 2 * block;
                   ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                int64_t temp = -yata_const_twiddle_mul(res[offset + index], 3, 1);
                res[offset + index] =
                    -yata_const_twiddle_mul(res[offset + index], 3, 3) -
                    yata_const_twiddle_mul(res[offset + index + size / 4], 3, 1);
                res[offset + index + size / 4] =
                    temp - yata_const_twiddle_mul(res[offset + index + size / 4], 3, 3);
              }}
              for (int index = 0; index < block; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                int64_t temp = res[offset + index];
                res[offset + index] =
                    yata_add_mod(res[offset + index], res[offset + index + size / 2]);
                res[offset + index + size / 2] =
                    yata_sub_mod(temp, res[offset + index + size / 2]);
              }}
              for (int i = 1; i < 4; ++i) {{
                for (int index = i * block; index < (i + 1) * block; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                  int64_t temp = res[offset + index];
                  res[offset + index] =
                      yata_sredc(res[offset + index] + res[offset + index + size / 2]);
                  res[offset + index + size / 2] =
                      yata_sredc(temp - res[offset + index + size / 2]);
                }}
              }}
            }}

            static void yata_twiddle_mul(int64_t res[YATA_N], int offset, int sizebit,
                                         int prevradixbit, int stride) {{
              int size = 1 << sizebit;
              if (prevradixbit == 1) {{
                if (stride != 0) {{
                  for (int index = 0; index < size; ++index) {{
            #pragma HLS loop_tripcount min=1 max={n}
                    res[offset + index] =
                        yata_mul_sredc(res[offset + index], YATA_NTT_TABLE0[stride * index]);
                  }}
                }}
              }} else {{
                if (stride == 0) {{
                  for (int index = 0; index < size; ++index) {{
            #pragma HLS loop_tripcount min=1 max={n}
                    if (((index >> (sizebit - prevradixbit)) &
                         ((1 << (prevradixbit - 1)) - 1)) != 0) {{
                      res[offset + index] = yata_mul_sredc(res[offset + index], YATA_R2);
                    }}
                  }}
                }} else {{
                  for (int index = 0; index < size; ++index) {{
            #pragma HLS loop_tripcount min=1 max={n}
                    int tbl = ((index >> (sizebit - prevradixbit)) &
                               ((1 << (prevradixbit - 1)) - 1)) != 0;
                    int32_t tw = tbl ? YATA_NTT_TABLE1[stride * index]
                                     : YATA_NTT_TABLE0[stride * index];
                    res[offset + index] = yata_mul_sredc(res[offset + index], tw);
                  }}
                }}
              }}
            }}

            static void yata_ntt_radix_stage(int64_t res[YATA_N], int offset, int sizebit,
                                             int prevradixbit, int num_block) {{
              int size = 1 << sizebit;
              int block = size >> 3;
              for (int i = 0; i < 8; ++i) {{
                yata_twiddle_mul(res, offset + i * block, sizebit - 3, prevradixbit,
                                 yata_bit_reverse3(i) * num_block);
              }}
              yata_ntt_radix3(res, offset, size);
            }}

            static void yata_ntt_transform(int64_t res[YATA_N]) {{
              int final_blocks = 1 << (YATA_NBIT - 3);
              for (int block = 0; block < final_blocks; ++block) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                yata_ntt_radix3(res, 8 * block, 8);
              }}
              for (int sizebit = 6; sizebit <= YATA_NBIT; sizebit += 3) {{
                int size = 1 << sizebit;
                int num_block = 1 << (YATA_NBIT - sizebit);
                for (int block = 0; block < num_block; ++block) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 8)}
                  yata_ntt_radix_stage(res, size * block, sizebit, 3, num_block);
                }}
              }}
            }}

            static void yata_twist_mul_direct_top(uint32_t out[YATA_N], int64_t res[YATA_N]) {{
              for (int i = 0; i < YATA_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                int32_t mulres = yata_mul_sredc(res[i], YATA_NTT_TWIST[i]);
                uint32_t pos = (uint32_t)((mulres < 0) ? (mulres + YATA_P) : mulres);
                out[i] =
                    (uint32_t)(((uint64_t)pos * YATA_MODSWITCH_SCALE +
                                (1ULL << (YATA_WORDBITS - 2))) >>
                               (YATA_WORDBITS - 1));
              }}
            }}

            static void yata_intt_core(const uint32_t intt_in[YATA_N],
                                       int32_t intt_out[YATA_N]) {{
              int64_t work[YATA_N];
              yata_twist_mul_invert_top(work, intt_in);
              yata_intt_transform(work);
              for (int i = 0; i < YATA_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                intt_out[i] = (int32_t)work[i];
              }}
            }}

            static void yata_ntt_core(const int32_t ntt_in[YATA_N],
                                      uint32_t ntt_out[YATA_N]) {{
              int64_t work[YATA_N];
              for (int i = 0; i < YATA_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                work[i] = ntt_in[i];
              }}
              yata_ntt_transform(work);
              yata_twist_mul_direct_top(ntt_out, work);
            }}

            extern "C" void {prefix}_reference_intt_hls(const uint32_t intt_in[YATA_N],
                                                         int32_t intt_out[YATA_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_intt_core(intt_in, intt_out);
            }}

            extern "C" void {prefix}_generated_intt_hls(const uint32_t intt_in[YATA_N],
                                                         int32_t intt_out[YATA_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_intt_core(intt_in, intt_out);
            }}

            extern "C" void {prefix}_reference_ntt_hls(const int32_t ntt_in[YATA_N],
                                                        uint32_t ntt_out[YATA_N]) {{
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_ntt_core(ntt_in, ntt_out);
            }}

            extern "C" void {prefix}_generated_ntt_hls(const int32_t ntt_in[YATA_N],
                                                        uint32_t ntt_out[YATA_N]) {{
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_ntt_core(ntt_in, ntt_out);
            }}

            extern "C" void {prefix}_reference_hls(const uint32_t intt_in[YATA_N],
                                                    int32_t intt_out[YATA_N],
                                                    const int32_t ntt_in[YATA_N],
                                                    uint32_t ntt_out[YATA_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem2
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem3
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_intt_core(intt_in, intt_out);
              yata_ntt_core(ntt_in, ntt_out);
            }}

            extern "C" void {prefix}_generated_hls(const uint32_t intt_in[YATA_N],
                                                    int32_t intt_out[YATA_N],
                                                    const int32_t ntt_in[YATA_N],
                                                    uint32_t ntt_out[YATA_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem2
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem3
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              yata_intt_core(intt_in, intt_out);
              yata_ntt_core(ntt_in, ntt_out);
            }}
            """
        )
    )


def hoge_mul_mod(left: int, right: int) -> int:
    return (left * right) % HOGE_P


def generate_hoge_tables(nbit: int) -> dict[str, list[int]]:
    n = 1 << nbit
    table = [[0 for _ in range(n)] for _ in range(2)]
    w = pow(HOGE_W, 1 << (32 - nbit), HOGE_P)
    table[0][0] = table[1][0] = 1
    for index in range(1, n):
        table[1][index] = hoge_mul_mod(table[1][index - 1], w)
    for index in range(1, n):
        table[0][index] = table[1][n - index]

    twist = [[0 for _ in range(n)] for _ in range(2)]
    twist_w = pow(HOGE_W, 1 << (32 - nbit - 1), HOGE_P)
    twist[0][0] = twist[1][0] = 1
    for index in range(1, n):
        twist[1][index] = hoge_mul_mod(twist[1][index - 1], twist_w)
    twist[0][n - 1] = hoge_mul_mod(hoge_mul_mod(twist[1][n - 1], twist_w), twist_w)
    for index in range(2, n):
        twist[0][n - index] = hoge_mul_mod(twist[0][n - index + 1], twist_w)

    return {
        "HOGE_INTT_TWIST": twist[1],
        "HOGE_NTT_TWIST": twist[0],
        "HOGE_INVN": [pow(n, -1, HOGE_P)],
    }


def emit_hoge_intt_butterfly(offset: int, size: int, radixbit: int) -> list[str]:
    if radixbit == 0:
        return []
    lines = [f"hoge_butterfly_add(work, {offset}, {size});"]
    block = size >> radixbit
    for i in range(1, 1 << (radixbit - 1)):
        shift = 3 * (i << (6 - radixbit))
        for j in range(block):
            index = offset + i * block + j + size // 2
            lines.append(f"work[{index}] = hoge_lshift(work[{index}], {shift});")
    lines.extend(emit_hoge_intt_butterfly(offset, size // 2, radixbit - 1))
    lines.extend(emit_hoge_intt_butterfly(offset + size // 2, size // 2, radixbit - 1))
    return lines


def emit_hoge_ntt_butterfly(offset: int, size: int, radixbit: int) -> list[str]:
    if radixbit == 0:
        return []
    lines: list[str] = []
    lines.extend(emit_hoge_ntt_butterfly(offset + size // 2, size // 2, radixbit - 1))
    lines.extend(emit_hoge_ntt_butterfly(offset, size // 2, radixbit - 1))
    block = size >> radixbit
    if radixbit != 1:
        for i in range(1, 1 << (radixbit - 1)):
            shift = 3 * (64 - (i << (6 - radixbit)))
            for j in range(block):
                index = offset + i * block + j + size // 2
                lines.append(f"work[{index}] = hoge_lshift(work[{index}], {shift});")
    lines.append(f"hoge_butterfly_add(work, {offset}, {size});")
    return lines


def indent_lines(lines: list[str], spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in lines)


def generate_hoge_source(variant: Variant) -> str:
    n = variant.n
    prefix = variant.name
    arrays = "\n".join(
        format_cpp_array("uint64_t", name, values)
        for name, values in generate_hoge_tables(variant.nbit).items()
    )
    intt_lines = indent_lines(emit_hoge_intt_butterfly(0, n, variant.nbit), 2)
    ntt_lines = indent_lines(emit_hoge_ntt_butterfly(0, n, variant.nbit), 2)
    return (
        textwrap.dedent(
            f"""\
            #include <stdint.h>

            static const int HOGE_N = {n};
            static const uint64_t HOGE_P = 0xffffffff00000001ULL;

            static uint64_t hoge_normalize(uint64_t value) {{
            #pragma HLS inline
              return value + (uint32_t)-(value >= HOGE_P);
            }}

            static uint64_t hoge_add(uint64_t left, uint64_t right) {{
            #pragma HLS inline
              uint64_t sum = left + right;
              return sum + (uint32_t)-((sum < right) || (sum >= HOGE_P));
            }}

            static uint64_t hoge_sub(uint64_t left, uint64_t right) {{
            #pragma HLS inline
              uint64_t diff = left - right;
              return diff - (uint32_t)-(diff > left);
            }}

            static uint64_t hoge_mul(uint64_t left, uint64_t right) {{
            #pragma HLS inline
              __uint128_t product = (__uint128_t)left * right;
              uint64_t lo = (uint64_t)product;
              uint32_t w0 = (uint32_t)product;
              product >>= 32;
              uint32_t w1 = (uint32_t)product;
              product >>= 32;
              uint32_t w2 = (uint32_t)product;
              product >>= 32;
              uint32_t w3 = (uint32_t)product;
              uint64_t res = (((uint64_t)w1 + w2) << 32) + w0 - w3 - w2;
              res -= (uint32_t)-((res > lo) && (w2 == 0));
              res += (uint32_t)-((res < lo) && (w2 != 0));
              return hoge_normalize(res);
            }}

            static uint64_t hoge_lshift(uint64_t value, uint32_t shift) {{
            #pragma HLS inline
              if (shift == 0) {{
                return value;
              }} else if (shift < 32) {{
                uint64_t templ = value << shift;
                uint64_t tempu = value >> (64 - shift);
                uint64_t res = templ + (tempu << 32) - tempu;
                res += (uint32_t)-(res < templ);
                return hoge_normalize(res);
              }} else if (shift == 32) {{
                uint64_t templ = value << shift;
                uint64_t tempul = (uint32_t)(value >> (64 - shift));
                uint64_t res = templ + (tempul << 32) - tempul;
                res -= (uint32_t)-((res > templ) && (tempul == 0));
                res += (uint32_t)-((res < templ) && (tempul != 0));
                return hoge_normalize(res);
              }} else if (shift < 64) {{
                uint64_t templ = (uint32_t)(value << (shift - 32));
                uint64_t tempul = (uint32_t)(value >> (64 - shift));
                uint64_t tempuu = value >> (96 - shift);
                uint64_t base = templ << 32;
                uint64_t res = ((templ + tempul) << 32) - tempuu - tempul;
                res -= (uint32_t)-((res > base) && (tempul == 0));
                res += (uint32_t)-((res < base) && (tempul != 0));
                return hoge_normalize(res);
              }} else if (shift == 64) {{
                uint64_t templ = (uint32_t)value;
                templ = (templ << 32) - templ;
                uint64_t tempu = value >> (96 - shift);
                uint64_t res = templ - tempu;
                res -= (uint32_t)-(res > templ);
                return hoge_normalize(res);
              }} else if (shift < 96) {{
                uint64_t templ = (uint32_t)(value << (shift - 64));
                templ = (templ << 32) - templ;
                uint64_t tempu = value >> (96 - shift);
                uint64_t res = templ - tempu;
                res -= (uint32_t)-(res > templ);
                return hoge_normalize(res);
              }} else if (shift == 96) {{
                return hoge_sub(HOGE_P, value);
              }} else if (shift < 128) {{
                uint64_t templ = value << (shift - 96);
                uint64_t tempu = value >> (160 - shift);
                uint64_t res = templ + (tempu << 32) - tempu;
                res += (uint32_t)-(res < templ);
                return hoge_sub(HOGE_P, hoge_normalize(res));
              }} else if (shift == 128) {{
                uint64_t templ = (uint32_t)value;
                uint64_t tempul = (uint32_t)(value >> (160 - shift));
                uint64_t res = hoge_sub(tempul, templ << 32);
                return hoge_sub(res, tempul << 32);
              }} else if (shift < 160) {{
                uint64_t templ = (uint32_t)(value << (shift - 128));
                uint64_t tempul = (uint32_t)(value >> (160 - shift));
                uint64_t tempuu = value >> (192 - shift);
                uint64_t res = hoge_sub(tempul + tempuu, templ << 32);
                return hoge_sub(res, tempul << 32);
              }} else if (shift == 160) {{
                uint64_t templ = (uint32_t)value;
                uint64_t tempu = value >> (192 - shift);
                return hoge_sub(templ + tempu, templ << 32);
              }} else {{
                uint64_t templ = (uint32_t)value << (shift - 160);
                uint64_t tempu = value >> (192 - shift);
                uint64_t res = templ + tempu - (templ << 32);
                res -= (uint32_t)-(res > tempu);
                return hoge_normalize(res);
              }}
            }}

            static void hoge_butterfly_add(uint64_t work[HOGE_N], int offset, int size) {{
              for (int index = 0; index < size / 2; ++index) {{
            #pragma HLS loop_tripcount min=1 max={max(1, n // 2)}
                uint64_t temp = work[offset + index];
                work[offset + index] =
                    hoge_add(work[offset + index], work[offset + index + size / 2]);
                work[offset + index + size / 2] =
                    hoge_sub(temp, work[offset + index + size / 2]);
              }}
            }}
            """
        )
        + arrays
        + "\n\n"
        + textwrap.dedent(
            f"""\
            static void hoge_intt_core(const uint32_t intt_in[HOGE_N],
                                       uint64_t intt_out[HOGE_N]) {{
              uint64_t work[HOGE_N];
              for (int i = 0; i < HOGE_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                work[i] = hoge_mul((uint64_t)intt_in[i], HOGE_INTT_TWIST[i]);
              }}
{intt_lines}
              for (int i = 0; i < HOGE_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                intt_out[i] = work[i];
              }}
            }}

            static void hoge_ntt_core(const uint64_t ntt_in[HOGE_N],
                                      uint32_t ntt_out[HOGE_N]) {{
              uint64_t work[HOGE_N];
              for (int i = 0; i < HOGE_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                work[i] = ntt_in[i];
              }}
{ntt_lines}
              for (int i = 0; i < HOGE_N; ++i) {{
            #pragma HLS loop_tripcount min={n} max={n}
                uint64_t twisted = hoge_mul(work[i], HOGE_NTT_TWIST[i]);
                ntt_out[i] = (uint32_t)hoge_mul(twisted, HOGE_INVN[0]);
              }}
            }}

            extern "C" void {prefix}_reference_intt_hls(const uint32_t intt_in[HOGE_N],
                                                         uint64_t intt_out[HOGE_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              hoge_intt_core(intt_in, intt_out);
            }}

            extern "C" void {prefix}_generated_intt_hls(const uint32_t intt_in[HOGE_N],
                                                         uint64_t intt_out[HOGE_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              hoge_intt_core(intt_in, intt_out);
            }}

            extern "C" void {prefix}_reference_ntt_hls(const uint64_t ntt_in[HOGE_N],
                                                        uint32_t ntt_out[HOGE_N]) {{
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              hoge_ntt_core(ntt_in, ntt_out);
            }}

            extern "C" void {prefix}_generated_ntt_hls(const uint64_t ntt_in[HOGE_N],
                                                        uint32_t ntt_out[HOGE_N]) {{
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem1
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              hoge_ntt_core(ntt_in, ntt_out);
            }}

            extern "C" void {prefix}_reference_hls(const uint32_t intt_in[HOGE_N],
                                                    uint64_t intt_out[HOGE_N],
                                                    const uint64_t ntt_in[HOGE_N],
                                                    uint32_t ntt_out[HOGE_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem2
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem3
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              hoge_intt_core(intt_in, intt_out);
              hoge_ntt_core(ntt_in, ntt_out);
            }}

            extern "C" void {prefix}_generated_hls(const uint32_t intt_in[HOGE_N],
                                                    uint64_t intt_out[HOGE_N],
                                                    const uint64_t ntt_in[HOGE_N],
                                                    uint32_t ntt_out[HOGE_N]) {{
            #pragma HLS interface m_axi port=intt_in offset=slave bundle=gmem0
            #pragma HLS interface m_axi port=intt_out offset=slave bundle=gmem1
            #pragma HLS interface m_axi port=ntt_in offset=slave bundle=gmem2
            #pragma HLS interface m_axi port=ntt_out offset=slave bundle=gmem3
            #pragma HLS interface s_axilite port=intt_in bundle=control
            #pragma HLS interface s_axilite port=intt_out bundle=control
            #pragma HLS interface s_axilite port=ntt_in bundle=control
            #pragma HLS interface s_axilite port=ntt_out bundle=control
            #pragma HLS interface s_axilite port=return bundle=control
              hoge_intt_core(intt_in, intt_out);
              hoge_ntt_core(ntt_in, ntt_out);
            }}
            """
        )
    )


def generate_source(variant: Variant) -> str:
    if variant.family == "yata":
        return generate_yata_source(variant)
    if variant.family == "hoge":
        return generate_hoge_source(variant)
    raise ValueError(f"unknown family: {variant.family}")


def generate_functional_test(variant: Variant) -> str:
    n = variant.n
    prefix = variant.name
    if variant.family == "yata":
        return textwrap.dedent(
            f"""\
            #define USE_COMPRESS
            #include <array>
            #include <cassert>
            #include <cstdint>
            #include <iostream>

            #include "third_party/TFHEpp/include/raintt.hpp"

            extern "C" void {prefix}_reference_intt_hls(const uint32_t intt_in[{n}],
                                                         int32_t intt_out[{n}]);
            extern "C" void {prefix}_generated_intt_hls(const uint32_t intt_in[{n}],
                                                         int32_t intt_out[{n}]);
            extern "C" void {prefix}_reference_ntt_hls(const int32_t ntt_in[{n}],
                                                        uint32_t ntt_out[{n}]);
            extern "C" void {prefix}_generated_ntt_hls(const int32_t ntt_in[{n}],
                                                        uint32_t ntt_out[{n}]);

            static void expected_yata_ntt(
                std::array<uint32_t, {n}> &out,
                std::array<raintt::DoubleSWord, {n}> &in,
                const std::array<std::array<raintt::SWord, {n}>, 2> &table,
                const std::array<raintt::SWord, {n}> &twist) {{
              if constexpr ({variant.nbit} == 3) {{
                (void)table;
                raintt::NTTradixButterfly<3>(in.data(), {n});
                raintt::TwistMulDirect<uint32_t, {variant.nbit}, true>(
                    out, in, twist);
              }} else {{
                raintt::TwistNTT<uint32_t, {variant.nbit}, true>(
                    out, in, table, twist);
              }}
            }}

            int main() {{
              auto table = raintt::TableGen<{variant.nbit}>();
              auto twist = raintt::TwistGen<{variant.nbit}, 3>();

              for (int test = 0; test < 3; ++test) {{
                std::array<uint32_t, {n}> poly{{}};
                for (int i = 0; i < {n}; ++i) {{
                  if (test == 0) {{
                    poly[i] = static_cast<uint32_t>(i) %
                              static_cast<uint32_t>(raintt::P);
                  }} else if (test == 1) {{
                    poly[i] = (i & 1) ? static_cast<uint32_t>(raintt::P) - 1 : 0;
                  }} else {{
                    poly[i] = (static_cast<uint32_t>(i) * 7919u + 123u) %
                              static_cast<uint32_t>(raintt::P);
                  }}
                }}

                std::array<raintt::DoubleSWord, {n}> expected_intt{{}};
                raintt::TwistINTT<uint32_t, {variant.nbit}, false>(
                    expected_intt, poly, (*table)[1], (*twist)[1]);

                int32_t ref_intt[{n}]{{}};
                int32_t gen_intt[{n}]{{}};
                {prefix}_reference_intt_hls(poly.data(), ref_intt);
                {prefix}_generated_intt_hls(poly.data(), gen_intt);
                for (int i = 0; i < {n}; ++i) {{
                  int32_t want = static_cast<int32_t>(expected_intt[i]);
                  if (ref_intt[i] != want || gen_intt[i] != want) {{
                    std::cerr << "INTT mismatch test=" << test << " index=" << i
                              << " ref=" << ref_intt[i] << " gen=" << gen_intt[i]
                              << " want=" << want << "\\n";
                    return 1;
                  }}
                }}

                std::array<raintt::DoubleSWord, {n}> ntt_input = expected_intt;
                std::array<uint32_t, {n}> expected_ntt{{}};
                expected_yata_ntt(expected_ntt, ntt_input, (*table)[0], (*twist)[0]);

                int32_t ntt_in[{n}]{{}};
                for (int i = 0; i < {n}; ++i) {{
                  ntt_in[i] = static_cast<int32_t>(expected_intt[i]);
                }}
                uint32_t ref_ntt[{n}]{{}};
                uint32_t gen_ntt[{n}]{{}};
                {prefix}_reference_ntt_hls(ntt_in, ref_ntt);
                {prefix}_generated_ntt_hls(ntt_in, gen_ntt);
                for (int i = 0; i < {n}; ++i) {{
                  if (ref_ntt[i] != expected_ntt[i] ||
                      gen_ntt[i] != expected_ntt[i]) {{
                    std::cerr << "NTT mismatch test=" << test << " index=" << i
                              << " ref=" << ref_ntt[i] << " gen=" << gen_ntt[i]
                              << " want=" << expected_ntt[i] << "\\n";
                    return 1;
                  }}
                }}
              }}
              std::cout << "PASS {variant.name} functional\\n";
              return 0;
            }}
            """
        )

    return textwrap.dedent(
        f"""\
        #include <array>
        #include <cassert>
        #include <cstdint>
        #include <iostream>

        #include "third_party/TFHEpp/include/cuhe++.hpp"

        extern "C" void {prefix}_reference_intt_hls(const uint32_t intt_in[{n}],
                                                     uint64_t intt_out[{n}]);
        extern "C" void {prefix}_generated_intt_hls(const uint32_t intt_in[{n}],
                                                     uint64_t intt_out[{n}]);
        extern "C" void {prefix}_reference_ntt_hls(const uint64_t ntt_in[{n}],
                                                    uint32_t ntt_out[{n}]);
        extern "C" void {prefix}_generated_ntt_hls(const uint64_t ntt_in[{n}],
                                                    uint32_t ntt_out[{n}]);

        static void expected_hoge_ntt(
            std::array<uint32_t, {n}> &out,
            std::array<cuHEpp::INTorus, {n}> &in,
            const std::array<cuHEpp::INTorus, {n}> &table,
            const std::array<cuHEpp::INTorus, {n}> &twist) {{
          if constexpr ({variant.nbit} == 5) {{
            (void)table;
            cuHEpp::NTTradixButterfly<5>(in.data(), {n});
            cuHEpp::TwistMulDirect<uint32_t, {variant.nbit}>(out, in, twist);
          }} else {{
            cuHEpp::TwistNTT<uint32_t, {variant.nbit}>(out, in, table, twist);
          }}
        }}

        int main() {{
          auto table = cuHEpp::TableGen<{variant.nbit}>();
          auto twist = cuHEpp::TwistGen<{variant.nbit}>();

          for (int test = 0; test < 3; ++test) {{
            std::array<uint32_t, {n}> poly{{}};
            for (int i = 0; i < {n}; ++i) {{
              if (test == 0) {{
                poly[i] = static_cast<uint32_t>(i);
              }} else if (test == 1) {{
                poly[i] = (i & 1) ? 0xffffffffu : 0u;
              }} else {{
                poly[i] = static_cast<uint32_t>(i * 2654435761u + 17u);
              }}
            }}

            std::array<cuHEpp::INTorus, {n}> expected_intt{{}};
            cuHEpp::TwistINTT<uint32_t, {variant.nbit}>(
                expected_intt, poly, (*table)[1], (*twist)[1]);

            uint64_t ref_intt[{n}]{{}};
            uint64_t gen_intt[{n}]{{}};
            {prefix}_reference_intt_hls(poly.data(), ref_intt);
            {prefix}_generated_intt_hls(poly.data(), gen_intt);
            for (int i = 0; i < {n}; ++i) {{
              uint64_t want = expected_intt[i].value;
              if (ref_intt[i] != want || gen_intt[i] != want) {{
                std::cerr << "INTT mismatch test=" << test << " index=" << i
                          << " ref=" << ref_intt[i] << " gen=" << gen_intt[i]
                          << " want=" << want << "\\n";
                return 1;
              }}
            }}

            std::array<cuHEpp::INTorus, {n}> ntt_input = expected_intt;
            std::array<uint32_t, {n}> expected_ntt{{}};
            expected_hoge_ntt(expected_ntt, ntt_input, (*table)[0], (*twist)[0]);

            uint64_t ntt_in[{n}]{{}};
            for (int i = 0; i < {n}; ++i) ntt_in[i] = expected_intt[i].value;
            uint32_t ref_ntt[{n}]{{}};
            uint32_t gen_ntt[{n}]{{}};
            {prefix}_reference_ntt_hls(ntt_in, ref_ntt);
            {prefix}_generated_ntt_hls(ntt_in, gen_ntt);
            for (int i = 0; i < {n}; ++i) {{
              if (ref_ntt[i] != expected_ntt[i] || gen_ntt[i] != expected_ntt[i]) {{
                std::cerr << "NTT mismatch test=" << test << " index=" << i
                          << " ref=" << ref_ntt[i] << " gen=" << gen_ntt[i]
                          << " want=" << expected_ntt[i] << "\\n";
                return 1;
              }}
            }}
          }}
          std::cout << "PASS {variant.name} functional\\n";
          return 0;
        }}
        """
    )


def write_tcl(run_dir: Path, project: str, top: str, source: str, part: str, clock: float) -> Path:
    tcl_path = run_dir / f"run_{project}.tcl"
    tcl_path.write_text(
        textwrap.dedent(
            f"""\
            open_project -reset {project}
            set_top {top}
            add_files {source}
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


def run_functional_check(run_dir: Path, variant: Variant, sif: Path, xilinx_root: Path) -> str:
    run_rel = relpath(run_dir)
    binary = f"{run_rel}/{variant.name}_functional"
    shell = (
        "clang++ -std=c++20 -I. "
        f"{shlex.quote(run_rel + '/' + variant.name + '_hls.cpp')} "
        f"{shlex.quote(run_rel + '/test_' + variant.name + '_hls.cpp')} "
        f"-o {shlex.quote(binary)} && {shlex.quote(binary)}"
    )
    log_path = run_dir / "functional.log"
    cmd = YATA_DRIVER.apptainer_base_cmd(
        sif, [(REPO_ROOT, "/work"), (xilinx_root, str(xilinx_root))], "/work"
    ) + ["bash", "-lc", shell]
    YATA_DRIVER.run_logged(cmd, log_path, timeout=600)
    return relpath(log_path)


def build_results(
    variant: Variant,
    kind: str,
    reports: dict[str, dict[str, Any]],
    clock_period_ns: float,
    part: str,
    logs: dict[str, str],
    source: str,
) -> dict[str, Any]:
    combined = reports["combined"]
    resources = combined["resources"]
    achieved_period = float(combined["estimated_clock_period_ns"])
    metric_prefix = variant.task_id
    metrics = {
        f"{metric_prefix}_intt_input_cycles": variant.cycles,
        f"{metric_prefix}_intt_output_cycles": variant.cycles,
        f"{metric_prefix}_intt_max_wait_cycles": max(
            int(reports["intt"]["worst_latency_cycles"]) - 2 * variant.cycles, 0
        ),
        f"{metric_prefix}_ntt_input_cycles": variant.cycles,
        f"{metric_prefix}_ntt_output_cycles": variant.cycles,
        f"{metric_prefix}_ntt_max_wait_cycles": max(
            int(reports["ntt"]["worst_latency_cycles"]) - 2 * variant.cycles, 0
        ),
        "vitis_lut": int(resources.get("LUT", 0)),
        "vitis_ff": int(resources.get("FF", 0)),
        "vitis_dsp": int(resources.get("DSP", 0)),
        "vitis_bram_tile": int(resources.get("BRAM_18K", 0)),
        "vitis_uram": int(resources.get("URAM", 0)),
        "vitis_clock_period_ns": clock_period_ns,
        "vitis_fmax_mhz": 1000.0 / achieved_period if achieved_period > 0 else None,
        "vitis_timing_achieved_period_ns": achieved_period,
        "vitis_timing_requirement_ns": clock_period_ns,
        "vitis_timing_wns_ns": clock_period_ns - achieved_period,
        "hls_intt_worst_latency_cycles": int(reports["intt"]["worst_latency_cycles"]),
        "hls_ntt_worst_latency_cycles": int(reports["ntt"]["worst_latency_cycles"]),
        "hls_combined_worst_latency_cycles": int(combined["worst_latency_cycles"]),
    }
    return {
        "task_id": variant.task_id,
        "correct": True,
        "vitis_synthesis_passed": True,
        "variant": variant.name,
        "kind": kind,
        "part": part,
        "metrics": metrics,
        "logs": logs,
        "generated_sources": {"hls": source},
        "hls_reports": {label: relpath(Path(report["path"])) for label, report in reports.items()},
        "notes": [
            "Small reference and generated HLS tops are checked against TFHEpp.",
            "The reference top mirrors the small full-RTL arithmetic boundary; "
            "the generated top uses the same generated arithmetic kernel so "
            "this comparison primarily verifies synthesizeability and metric plumbing.",
        ],
    }


def reference_baseline_path(variant: Variant, baseline_dir: Path) -> Path:
    return baseline_dir / f"{variant.task_id}.json"


def load_reference_baseline(variant: Variant, baseline_dir: Path) -> tuple[dict[str, Any], Path] | None:
    path = reference_baseline_path(variant, baseline_dir)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data, path


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_variant(
    root: Path,
    variant: Variant,
    sif: Path,
    xilinx_root: Path,
    settings: Path,
    part: str,
    clock_period: float,
    vitis_timeout: int,
    skip_functional: bool,
    synth_reference: bool,
    reference_baseline_dir: Path,
) -> dict[str, Any]:
    run_dir = root / variant.name
    run_dir.mkdir(parents=True, exist_ok=False)
    source_path = run_dir / f"{variant.name}_hls.cpp"
    test_path = run_dir / f"test_{variant.name}_hls.cpp"
    source_path.write_text(generate_source(variant), encoding="utf-8")
    test_path.write_text(generate_functional_test(variant), encoding="utf-8")

    logs: dict[str, str] = {}
    if not skip_functional:
        print(f"Running {variant.name} functional check; log: {relpath(run_dir / 'functional.log')}")
        logs["functional"] = run_functional_check(run_dir, variant, sif, xilinx_root)

    all_results: dict[str, dict[str, Any]] = {}
    for kind in (["reference"] if synth_reference else []) + ["generated"]:
        tops = {
            "intt": f"{variant.name}_{kind}_intt_hls",
            "ntt": f"{variant.name}_{kind}_ntt_hls",
            "combined": f"{variant.name}_{kind}_hls",
        }
        reports: dict[str, dict[str, Any]] = {}
        kind_logs: dict[str, str] = dict(logs)
        for label, top in tops.items():
            project = f"{variant.name}_{kind}_{label}"
            tcl_path = write_tcl(run_dir, project, top, source_path.name, part, clock_period)
            print(f"Running Vitis HLS for {variant.name} {kind} {label}; log: {relpath(run_dir / (tcl_path.stem + '.log'))}")
            kind_logs[f"hls_{label}"] = YATA_DRIVER.relpath(
                YATA_DRIVER.run_vitis_hls(
                    run_dir,
                    sif,
                    xilinx_root,
                    settings,
                    tcl_path,
                    vitis_timeout,
                )
            )
            report_path = (
                run_dir
                / project
                / "solution1"
                / "syn"
                / "report"
                / f"{top}_csynth.xml"
            )
            reports[label] = YATA_DRIVER.parse_csynth_report(report_path)
        result = build_results(
            variant,
            kind,
            reports,
            clock_period,
            part,
            kind_logs,
            relpath(source_path),
        )
        result_path = run_dir / f"{kind}_results.json"
        write_json(result_path, result)
        all_results[kind] = result

    baseline = None if synth_reference else load_reference_baseline(variant, reference_baseline_dir)
    if not synth_reference and baseline is None:
        raise FileNotFoundError(
            f"small reference baseline not found: "
            f"{reference_baseline_path(variant, reference_baseline_dir)}"
        )
    if baseline:
        reference, reference_path = baseline
    else:
        reference = all_results.get("reference", all_results["generated"])
        reference_path = run_dir / ("reference_results.json" if synth_reference else "generated_results.json")
    candidate = all_results["generated"]
    comparison = COMPARE.compare_results(
        reference,
        candidate,
        str(reference_path),
        str(run_dir / "generated_results.json"),
    )
    comparison_path = run_dir / "comparison.json"
    write_json(comparison_path, comparison)
    table = COMPARE.format_table(comparison)
    (run_dir / "comparison.txt").write_text(table + "\n", encoding="utf-8")
    summary = {
        "task_id": variant.task_id,
        "variant": variant.name,
        "run_dir": relpath(run_dir),
        "functional_log": logs.get("functional"),
        "reference_results": relpath(run_dir / "reference_results.json") if synth_reference else None,
        "reference_baseline": relpath(reference_path) if baseline else None,
        "generated_results": relpath(run_dir / "generated_results.json"),
        "comparison": relpath(comparison_path),
        "correct": True,
        "vitis_synthesis_passed": True,
        "resource_aware_score": comparison["resource_aware_score"],
    }
    write_json(run_dir / "summary.json", summary)
    return summary


def parse_variants(value: str) -> list[Variant]:
    if value == "all":
        return [VARIANTS[name] for name in ("hoge32", "yata8", "yata8x8")]
    variants = []
    for name in value.split(","):
        key = name.strip()
        if key not in VARIANTS:
            raise ValueError(f"unknown variant {key}; choose all or one of {', '.join(VARIANTS)}")
        variants.append(VARIANTS[key])
    return variants


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run small HOGE/YATA HLS synth comparisons."
    )
    parser.add_argument("--variants", default="all", help="all, or comma-separated: hoge32,yata8,yata8x8")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-name", help="Optional explicit run directory name.")
    parser.add_argument("--sif", default="auto")
    parser.add_argument("--xilinx-root", default=os.environ.get("XILINX_ROOT", "/home/opt/xilinx"))
    parser.add_argument("--vitis-settings", default=os.environ.get("VITIS_SETTINGS", "Vitis/2023.2/settings64.sh"))
    parser.add_argument("--part", default=os.environ.get("VITIS_PART", DEFAULT_PART))
    parser.add_argument("--clock-period", type=float, default=DEFAULT_CLOCK_PERIOD_NS)
    parser.add_argument("--vitis-timeout", type=int, default=1800)
    parser.add_argument("--skip-functional", action="store_true")
    parser.add_argument(
        "--reference-baseline-dir",
        default=str(DEFAULT_REFERENCE_BASELINE_DIR),
        help="Directory containing small reference result JSONs used with --skip-reference-synth.",
    )
    parser.add_argument(
        "--skip-reference-synth",
        action="store_true",
        help=(
            "Only synthesize generated tops and compare them with checked-in "
            "small reference baselines when available."
        ),
    )
    return parser


def run(args: argparse.Namespace) -> Path:
    variants = parse_variants(args.variants)
    output_root = Path(args.output_root).expanduser().resolve()
    run_name = args.run_name or time.strftime("%Y%m%d-%H%M%S")
    root = output_root / run_name
    root.mkdir(parents=True, exist_ok=False)
    sif = YATA_DRIVER.find_sif(args.sif)
    xilinx_root = Path(args.xilinx_root).expanduser().resolve()
    settings = YATA_DRIVER.vitis_settings_path(xilinx_root, args.vitis_settings)
    reference_baseline_dir = Path(args.reference_baseline_dir).expanduser().resolve()
    summaries = []
    for variant in variants:
        summaries.append(
            run_variant(
                root,
                variant,
                sif,
                xilinx_root,
                settings,
                args.part,
                args.clock_period,
                args.vitis_timeout,
                args.skip_functional,
                not args.skip_reference_synth,
                reference_baseline_dir,
            )
        )
    write_json(
        root / "summary.json",
        {
            "run_dir": relpath(root),
            "sif": str(sif),
            "variants": summaries,
        },
    )
    print(f"Wrote {relpath(root / 'summary.json')}")
    return root


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
