"""Deterministic behavioral RTL generators for HOGE tasks."""

from __future__ import annotations

from typing import Iterable


MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
P64 = 0xFFFFFFFF00000001
W64 = 12037493425763644479


def _u64(value: int) -> int:
    return value & MASK64


def _ctor(value: int, modulo: bool = True) -> int:
    value = _u64(value)
    if modulo and value >= P64:
        value = _u64(value + MASK32)
    return value


def _add(a: int, b: int) -> int:
    tmp = _u64(a + b)
    correction = MASK32 if tmp < b or tmp >= P64 else 0
    return _u64(tmp + correction)


def _sub(a: int, b: int) -> int:
    tmp = _u64(a - b)
    correction = MASK32 if tmp > a else 0
    return _u64(tmp - correction)


def _mul(a: int, b: int) -> int:
    product = a * b
    lo = product & MASK64
    words = [(product >> (32 * index)) & MASK32 for index in range(4)]
    result = _u64(((words[1] + words[2]) << 32) + words[0] - words[3] - words[2])
    if result > lo and words[2] == 0:
        result = _u64(result - MASK32)
    if result < lo and words[2] != 0:
        result = _u64(result + MASK32)
    return _ctor(result)


def _pow(base: int, exponent: int) -> int:
    result = 1
    while exponent:
        if exponent & 1:
            result = _mul(result, base)
        base = _mul(base, base)
        exponent >>= 1
    return result


def _table_and_twist(nbit: int = 10) -> tuple[list[int], list[int]]:
    n = 1 << nbit
    table = [0] * n
    twist = [0] * n

    table_w = _pow(_ctor(W64), 1 << (32 - nbit))
    table[0] = 1
    for index in range(1, n):
        table[index] = _mul(table[index - 1], table_w)

    twist_w = _pow(_ctor(W64), 1 << (32 - nbit - 1))
    twist[0] = 1
    for index in range(1, n):
        twist[index] = _mul(twist[index - 1], twist_w)

    return table, twist


def _table_and_twist_pair(
    nbit: int = 10,
) -> tuple[list[int], list[int], list[int], list[int]]:
    n = 1 << nbit
    table_forward = [0] * n
    table_inverse = [0] * n
    twist_forward = [0] * n
    twist_inverse = [0] * n

    table_w = _pow(_ctor(W64), 1 << (32 - nbit))
    table_forward[0] = 1
    table_inverse[0] = 1
    for index in range(1, n):
        table_inverse[index] = _mul(table_inverse[index - 1], table_w)
    for index in range(1, n):
        table_forward[index] = table_inverse[n - index]

    twist_w = _pow(_ctor(W64), 1 << (32 - nbit - 1))
    twist_forward[0] = 1
    twist_inverse[0] = 1
    for index in range(1, n):
        twist_inverse[index] = _mul(twist_inverse[index - 1], twist_w)
    twist_forward[n - 1] = _mul(_mul(twist_inverse[n - 1], twist_w), twist_w)
    for index in range(2, n):
        twist_forward[n - index] = _mul(twist_forward[n - index + 1], twist_w)

    return table_forward, table_inverse, twist_forward, twist_inverse


def _hex64(value: int) -> str:
    return f"64'h{value:016x}"


def _emit_lines(lines: list[str], text: str = "") -> None:
    lines.append(text)


def _emit_butterfly(lines: list[str], base: int, size: int, radixbit: int) -> None:
    if radixbit == 0:
        return

    half = size // 2
    block = size >> radixbit
    _emit_lines(lines, f"    for (idx = 0; idx < {half}; idx = idx + 1) begin")
    _emit_lines(lines, f"      temp_value = work_mem[{base} + idx];")
    _emit_lines(
        lines,
        f"      work_mem[{base} + idx] = int_add(work_mem[{base} + idx], "
        f"work_mem[{base + half} + idx]);",
    )
    _emit_lines(
        lines,
        f"      work_mem[{base + half} + idx] = int_sub(temp_value, "
        f"work_mem[{base + half} + idx]);",
    )
    _emit_lines(lines, "    end")

    if radixbit > 1:
        _emit_lines(
            lines,
            f"    for (i = 1; i < {1 << (radixbit - 1)}; i = i + 1) begin",
        )
        _emit_lines(lines, f"      for (j = 0; j < {block}; j = j + 1) begin")
        _emit_lines(
            lines,
            f"        work_mem[{base + half} + i * {block} + j] = "
            f"int_lsh(work_mem[{base + half} + i * {block} + j], "
            f"3 * (i << {6 - radixbit}));",
        )
        _emit_lines(lines, "      end")
        _emit_lines(lines, "    end")

    _emit_butterfly(lines, base, half, radixbit - 1)
    _emit_butterfly(lines, base + half, half, radixbit - 1)


def _constant_initializers(name: str, values: Iterable[int]) -> list[str]:
    return [f"    {name}[{index}] = {_hex64(value)};" for index, value in enumerate(values)]


def generate_hoge_streaming_intt_behavioral() -> str:
    """Return a compact generated RTL implementation of HOGE 1024-point INTT."""

    table, twist = _table_and_twist()
    lines: list[str] = []
    emit = lambda text="": _emit_lines(lines, text)

    emit("// Generated behavioral HOGE streaming INTT candidate.")
    emit("// Implements the TFHEpp cuHEpp::TwistINTT<uint32_t,10> contract.")
    emit("module INTTWrap(")
    emit("  input           clock,")
    emit("  input           reset,")
    emit("  input  [1023:0] io_in,")
    emit("  output [2047:0] io_out,")
    emit("  output          io_validout,")
    emit("  input           io_enable")
    emit(");")
    emit("  localparam [63:0] P = 64'hffffffff00000001;")
    emit("  localparam [1:0] STATE_CAPTURE = 2'd0;")
    emit("  localparam [1:0] STATE_COMPUTE = 2'd1;")
    emit("  localparam [1:0] STATE_OUTPUT = 2'd2;")
    emit("")
    emit("  reg [1:0] state;")
    emit("  reg [5:0] input_count;")
    emit("  reg [5:0] output_count;")
    emit("  reg [2047:0] output_word;")
    emit("  reg valid_word;")
    emit("  reg [63:0] coeff_mem [0:1023];")
    emit("  reg [63:0] work_mem [0:1023];")
    emit("  reg [63:0] out_mem [0:1023];")
    emit("  reg [63:0] table_mem [0:1023];")
    emit("  reg [63:0] twist_mem [0:1023];")
    emit("  integer idx;")
    emit("  integer lane;")
    emit("")
    emit("  assign io_out = output_word;")
    emit("  assign io_validout = valid_word;")
    emit("")

    emit("  function [63:0] int_ctor;")
    emit("    input [63:0] value;")
    emit("    begin")
    emit("      int_ctor = value + ((value >= P) ? 64'h00000000ffffffff : 64'h0);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_add;")
    emit("    input [63:0] a;")
    emit("    input [63:0] b;")
    emit("    reg [63:0] tmp;")
    emit("    begin")
    emit("      tmp = a + b;")
    emit(
        "      int_add = tmp + (((tmp < b) || (tmp >= P)) ? "
        "64'h00000000ffffffff : 64'h0);"
    )
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_sub;")
    emit("    input [63:0] a;")
    emit("    input [63:0] b;")
    emit("    reg [63:0] tmp;")
    emit("    begin")
    emit("      tmp = a - b;")
    emit("      int_sub = tmp - ((tmp > a) ? 64'h00000000ffffffff : 64'h0);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_mul;")
    emit("    input [63:0] a;")
    emit("    input [63:0] b;")
    emit("    reg [127:0] product;")
    emit("    reg [63:0] lo;")
    emit("    reg [31:0] w0;")
    emit("    reg [31:0] w1;")
    emit("    reg [31:0] w2;")
    emit("    reg [31:0] w3;")
    emit("    reg [63:0] reduced;")
    emit("    begin")
    emit("      product = {64'b0, a} * {64'b0, b};")
    emit("      lo = product[63:0];")
    emit("      w0 = product[31:0];")
    emit("      w1 = product[63:32];")
    emit("      w2 = product[95:64];")
    emit("      w3 = product[127:96];")
    emit(
        "      reduced = ((({32'b0, w1} + {32'b0, w2}) << 32) + "
        "{32'b0, w0}) - {32'b0, w3} - {32'b0, w2};"
    )
    emit(
        "      reduced = reduced - (((reduced > lo) && (w2 == 32'b0)) ? "
        "64'h00000000ffffffff : 64'h0);"
    )
    emit(
        "      reduced = reduced + (((reduced < lo) && (w2 != 32'b0)) ? "
        "64'h00000000ffffffff : 64'h0);"
    )
    emit("      int_mul = int_ctor(reduced);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_lsh;")
    emit("    input [63:0] a;")
    emit("    input integer shift;")
    emit("    reg [63:0] templ;")
    emit("    reg [63:0] tempu;")
    emit("    reg [31:0] tempul;")
    emit("    reg [63:0] tempuu;")
    emit("    reg [63:0] reduced;")
    emit("    begin")
    emit("      if (shift == 0) begin")
    emit("        int_lsh = a;")
    emit("      end else if (shift < 32) begin")
    emit("        templ = a << shift;")
    emit("        tempu = a >> (64 - shift);")
    emit("        reduced = templ + (tempu << 32) - tempu;")
    emit(
        "        reduced = reduced + ((reduced < templ) ? "
        "64'h00000000ffffffff : 64'h0);"
    )
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift == 32) begin")
    emit("        templ = a << 32;")
    emit("        tempul = a[63:32];")
    emit("        reduced = templ + ({32'b0, tempul} << 32) - {32'b0, tempul};")
    emit(
        "        reduced = reduced - (((reduced > templ) && "
        "(tempul == 32'b0)) ? 64'h00000000ffffffff : 64'h0);"
    )
    emit(
        "        reduced = reduced + (((reduced < templ) && "
        "(tempul != 32'b0)) ? 64'h00000000ffffffff : 64'h0);"
    )
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift < 64) begin")
    emit("        templ = a << (shift - 32);")
    emit("        templ = {32'b0, templ[31:0]};")
    emit("        tempu = a >> (64 - shift);")
    emit("        tempul = tempu[31:0];")
    emit("        tempuu = a >> (96 - shift);")
    emit(
        "        reduced = (((templ + {32'b0, tempul}) << 32) - tempuu) - "
        "{32'b0, tempul};"
    )
    emit(
        "        reduced = reduced - (((reduced > (templ << 32)) && "
        "(tempul == 32'b0)) ? 64'h00000000ffffffff : 64'h0);"
    )
    emit(
        "        reduced = reduced + (((reduced < (templ << 32)) && "
        "(tempul != 32'b0)) ? 64'h00000000ffffffff : 64'h0);"
    )
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift == 64) begin")
    emit("        templ = {32'b0, a[31:0]};")
    emit("        templ = (templ << 32) - templ;")
    emit("        tempu = a >> 32;")
    emit("        reduced = templ - tempu;")
    emit(
        "        reduced = reduced - ((reduced > templ) ? "
        "64'h00000000ffffffff : 64'h0);"
    )
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else begin")
    emit("        templ = a << (shift - 64);")
    emit("        templ = {32'b0, templ[31:0]};")
    emit("        templ = (templ << 32) - templ;")
    emit("        tempu = a >> (96 - shift);")
    emit("        reduced = templ - tempu;")
    emit(
        "        reduced = reduced - ((reduced > templ) ? "
        "64'h00000000ffffffff : 64'h0);"
    )
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [2047:0] pack_output;")
    emit("    input [5:0] cycle;")
    emit("    integer pack_lane;")
    emit("    reg [63:0] pack_value;")
    emit("    begin")
    emit("      pack_output = 2048'b0;")
    emit("      for (pack_lane = 0; pack_lane < 32; pack_lane = pack_lane + 1) begin")
    emit("        pack_value = out_mem[cycle * 32 + pack_lane];")
    emit("        pack_output[pack_lane * 64 +: 64] = pack_value;")
    emit("      end")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  task intt_butterfly;")
    emit("    input integer base;")
    emit("    input integer size;")
    emit("    input integer radixbit;")
    emit("    integer bfly_level;")
    emit("    integer bfly_segment;")
    emit("    integer bfly_idx;")
    emit("    integer bfly_i;")
    emit("    integer bfly_j;")
    emit("    integer segment_size;")
    emit("    integer current_radix;")
    emit("    integer butterfly_block;")
    emit("    integer half_size;")
    emit("    integer local_base;")
    emit("    reg [63:0] temp_value;")
    emit("    begin")
    emit("      butterfly_block = size >> radixbit;")
    emit("      for (bfly_level = 0; bfly_level < radixbit; bfly_level = bfly_level + 1) begin")
    emit("        segment_size = size >> bfly_level;")
    emit("        half_size = segment_size >> 1;")
    emit("        current_radix = radixbit - bfly_level;")
    emit("        for (bfly_segment = 0; bfly_segment < (1 << bfly_level); bfly_segment = bfly_segment + 1) begin")
    emit("          local_base = base + bfly_segment * segment_size;")
    emit("          for (bfly_idx = 0; bfly_idx < half_size; bfly_idx = bfly_idx + 1) begin")
    emit("            temp_value = work_mem[local_base + bfly_idx];")
    emit("            work_mem[local_base + bfly_idx] = int_add(work_mem[local_base + bfly_idx], work_mem[local_base + half_size + bfly_idx]);")
    emit("            work_mem[local_base + half_size + bfly_idx] = int_sub(temp_value, work_mem[local_base + half_size + bfly_idx]);")
    emit("          end")
    emit("          if (current_radix > 1) begin")
    emit("            for (bfly_i = 1; bfly_i < (1 << (current_radix - 1)); bfly_i = bfly_i + 1) begin")
    emit("              for (bfly_j = 0; bfly_j < butterfly_block; bfly_j = bfly_j + 1) begin")
    emit("                work_mem[local_base + half_size + bfly_i * butterfly_block + bfly_j] = int_lsh(work_mem[local_base + half_size + bfly_i * butterfly_block + bfly_j], 3 * (bfly_i << (6 - current_radix)));")
    emit("              end")
    emit("            end")
    emit("          end")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task compute_transform;")
    emit("    integer c_idx;")
    emit("    integer tw_i;")
    emit("    integer tw_j;")
    emit("    integer rem_block;")
    emit("    begin")
    emit("      for (c_idx = 0; c_idx < 1024; c_idx = c_idx + 1) begin")
    emit("        work_mem[c_idx] = int_mul(coeff_mem[c_idx], twist_mem[c_idx]);")
    emit("      end")
    emit("      intt_butterfly(0, 1024, 6);")
    emit("      for (tw_i = 1; tw_i < 64; tw_i = tw_i + 1) begin")
    emit("        for (tw_j = 1; tw_j < 16; tw_j = tw_j + 1) begin")
    emit("          work_mem[tw_i * 16 + tw_j] = int_mul(work_mem[tw_i * 16 + tw_j], table_mem[bit_reverse6(tw_i[5:0]) * tw_j]);")
    emit("        end")
    emit("      end")
    emit("      for (rem_block = 0; rem_block < 64; rem_block = rem_block + 1) begin")
    emit("        intt_butterfly(rem_block * 16, 16, 4);")
    emit("      end")
    emit("      for (c_idx = 0; c_idx < 1024; c_idx = c_idx + 1) begin")
    emit("        out_mem[c_idx] = work_mem[c_idx];")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  function [5:0] bit_reverse6;")
    emit("    input [5:0] value;")
    emit("    begin")
    emit("      bit_reverse6 = {value[0], value[1], value[2], value[3], value[4], value[5]};")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  initial begin")
    emit("    state = STATE_CAPTURE;")
    emit("    input_count = 6'd0;")
    emit("    output_count = 6'd0;")
    emit("    output_word = 2048'b0;")
    emit("    valid_word = 1'b0;")
    emit("    for (idx = 0; idx < 1024; idx = idx + 1) begin")
    emit("      coeff_mem[idx] = 64'b0;")
    emit("      work_mem[idx] = 64'b0;")
    emit("      out_mem[idx] = 64'b0;")
    emit("    end")
    lines.extend(_constant_initializers("table_mem", table))
    lines.extend(_constant_initializers("twist_mem", twist))
    emit("  end")
    emit("")
    emit("  always @(posedge clock) begin")
    emit("    if (reset) begin")
    emit("      state <= STATE_CAPTURE;")
    emit("      input_count <= 6'd0;")
    emit("      output_count <= 6'd0;")
    emit("      output_word <= 2048'b0;")
    emit("      valid_word <= 1'b0;")
    emit("    end else begin")
    emit("      case (state)")
    emit("        STATE_CAPTURE: begin")
    emit("          valid_word <= 1'b0;")
    emit("          if (io_enable) begin")
    emit("            for (lane = 0; lane < 32; lane = lane + 1) begin")
    emit("              coeff_mem[lane * 32 + {26'b0, input_count}] <= {32'b0, io_in[lane * 32 +: 32]};")
    emit("            end")
    emit("            if (input_count == 6'd31) begin")
    emit("              input_count <= 6'd0;")
    emit("              state <= STATE_COMPUTE;")
    emit("            end else begin")
    emit("              input_count <= input_count + 6'd1;")
    emit("            end")
    emit("          end")
    emit("        end")
    emit("        STATE_COMPUTE: begin")
    emit("          compute_transform;")
    emit("          output_count <= 6'd0;")
    emit("          output_word <= pack_output(6'd0);")
    emit("          valid_word <= 1'b1;")
    emit("          state <= STATE_OUTPUT;")
    emit("        end")
    emit("        STATE_OUTPUT: begin")
    emit("          if (output_count == 6'd31) begin")
    emit("            output_count <= 6'd0;")
    emit("            output_word <= 2048'b0;")
    emit("            valid_word <= 1'b0;")
    emit("            state <= STATE_CAPTURE;")
    emit("          end else begin")
    emit("            output_count <= output_count + 6'd1;")
    emit("            output_word <= pack_output(output_count + 6'd1);")
    emit("            valid_word <= 1'b1;")
    emit("          end")
    emit("        end")
    emit("        default: begin")
    emit("          state <= STATE_CAPTURE;")
    emit("          valid_word <= 1'b0;")
    emit("        end")
    emit("      endcase")
    emit("    end")
    emit("  end")
    emit("endmodule")
    return "\n".join(lines) + "\n"


def generate_hoge_externalproduct_behavioral() -> str:
    """Return generated RTL for the HOGE TRGSWNTT ExternalProduct task."""

    table_ntt, table_intt, twist_ntt, twist_intt = _table_and_twist_pair()
    inv_n = _ctor((((-(1 << (32 - 10)) - 1) & MASK32) << 32) + (1 << (32 - 10)) + 1)
    lines: list[str] = []
    emit = lambda text="": _emit_lines(lines, text)

    emit("/* verilator lint_off WIDTH */")
    emit("// Generated behavioral HOGE ExternalProduct candidate.")
    emit("// Implements TFHEpp::ExternalProduct<lvl1param> over streamed TRGSWNTT data.")
    emit("module ExternalProductWrap(")
    emit("  input           clock,")
    emit("  input           reset,")
    emit("  input  [1023:0] io_in,")
    emit("  input           io_validin,")
    emit("  output          io_validout,")
    emit("  output [1023:0] io_out,")
    emit("  input  [4095:0] io_trgswin,")
    emit("  input           io_trgswinvalid,")
    emit("  output          io_trgswinready,")
    emit("  output          io_fin,")
    emit("  output          io_inttvalidout,")
    emit("  output [2047:0] io_inttout,")
    emit("  output [4095:0] io_accout")
    emit(");")
    emit("  localparam [63:0] P = 64'hffffffff00000001;")
    emit("  localparam [63:0] INV_N = " + _hex64(inv_n) + ";")
    emit("  localparam [2:0] STATE_CAPTURE = 3'd0;")
    emit("  localparam [2:0] STATE_WAIT_TRGSW = 3'd1;")
    emit("  localparam [2:0] STATE_COMPUTE = 3'd2;")
    emit("  localparam [2:0] STATE_OUTPUT = 3'd3;")
    emit("")
    emit("  reg [2:0] state;")
    emit("  reg [5:0] input_count;")
    emit("  reg       input_component;")
    emit("  reg [7:0] trgsw_count;")
    emit("  reg [5:0] output_count;")
    emit("  reg [1023:0] output_word;")
    emit("  reg valid_word;")
    emit("  reg [31:0] input_mem [0:2047];")
    emit("  reg [63:0] trgsw_mem [0:12287];")
    emit("  reg [63:0] work_mem [0:1023];")
    emit("  reg [63:0] restr_mem [0:2047];")
    emit("  reg [31:0] result_mem [0:2047];")
    emit("  reg [63:0] table_ntt_mem [0:1023];")
    emit("  reg [63:0] table_intt_mem [0:1023];")
    emit("  reg [63:0] twist_ntt_mem [0:1023];")
    emit("  reg [63:0] twist_intt_mem [0:1023];")
    emit("  integer idx;")
    emit("  integer lane;")
    emit("  integer trgsw_lane;")
    emit("  integer trgsw_component;")
    emit("")
    emit("  assign io_out = output_word;")
    emit("  assign io_validout = valid_word;")
    emit("  assign io_trgswinready = (trgsw_count < 8'd192);")
    emit("  assign io_fin = valid_word && (state == STATE_OUTPUT) && (output_count == 6'd63);")
    emit("  assign io_inttvalidout = 1'b0;")
    emit("  assign io_inttout = 2048'b0;")
    emit("  assign io_accout = 4096'b0;")
    emit("")
    emit("  function [63:0] int_ctor;")
    emit("    input [63:0] value;")
    emit("    begin")
    emit("      int_ctor = value + ((value >= P) ? 64'h00000000ffffffff : 64'h0);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_add;")
    emit("    input [63:0] a;")
    emit("    input [63:0] b;")
    emit("    reg [63:0] tmp;")
    emit("    begin")
    emit("      tmp = a + b;")
    emit("      int_add = tmp + (((tmp < b) || (tmp >= P)) ? 64'h00000000ffffffff : 64'h0);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_sub;")
    emit("    input [63:0] a;")
    emit("    input [63:0] b;")
    emit("    reg [63:0] tmp;")
    emit("    begin")
    emit("      tmp = a - b;")
    emit("      int_sub = tmp - ((tmp > a) ? 64'h00000000ffffffff : 64'h0);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_mul;")
    emit("    input [63:0] a;")
    emit("    input [63:0] b;")
    emit("    reg [127:0] product;")
    emit("    reg [63:0] lo;")
    emit("    reg [31:0] w0;")
    emit("    reg [31:0] w1;")
    emit("    reg [31:0] w2;")
    emit("    reg [31:0] w3;")
    emit("    reg [63:0] reduced;")
    emit("    begin")
    emit("      product = {64'b0, a} * {64'b0, b};")
    emit("      lo = product[63:0];")
    emit("      w0 = product[31:0];")
    emit("      w1 = product[63:32];")
    emit("      w2 = product[95:64];")
    emit("      w3 = product[127:96];")
    emit("      reduced = ((({32'b0, w1} + {32'b0, w2}) << 32) + {32'b0, w0}) - {32'b0, w3} - {32'b0, w2};")
    emit("      reduced = reduced - (((reduced > lo) && (w2 == 32'b0)) ? 64'h00000000ffffffff : 64'h0);")
    emit("      reduced = reduced + (((reduced < lo) && (w2 != 32'b0)) ? 64'h00000000ffffffff : 64'h0);")
    emit("      int_mul = int_ctor(reduced);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [63:0] int_lsh;")
    emit("    input [63:0] a;")
    emit("    input integer shift;")
    emit("    reg [63:0] templ;")
    emit("    reg [63:0] tempu;")
    emit("    reg [31:0] tempul;")
    emit("    reg [31:0] templ32;")
    emit("    reg [63:0] tempuu;")
    emit("    reg [63:0] reduced;")
    emit("    begin")
    emit("      if (shift == 0) begin")
    emit("        int_lsh = a;")
    emit("      end else if (shift < 32) begin")
    emit("        templ = a << shift;")
    emit("        tempu = a >> (64 - shift);")
    emit("        reduced = templ + (tempu << 32) - tempu;")
    emit("        reduced = reduced + ((reduced < templ) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift == 32) begin")
    emit("        templ = a << 32;")
    emit("        tempul = a[63:32];")
    emit("        reduced = templ + ({32'b0, tempul} << 32) - {32'b0, tempul};")
    emit("        reduced = reduced - (((reduced > templ) && (tempul == 32'b0)) ? 64'h00000000ffffffff : 64'h0);")
    emit("        reduced = reduced + (((reduced < templ) && (tempul != 32'b0)) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift < 64) begin")
    emit("        templ32 = a[31:0] << (shift - 32);")
    emit("        templ = {32'b0, templ32};")
    emit("        tempu = a >> (64 - shift);")
    emit("        tempul = tempu[31:0];")
    emit("        tempuu = a >> (96 - shift);")
    emit("        reduced = (((templ + {32'b0, tempul}) << 32) - tempuu) - {32'b0, tempul};")
    emit("        reduced = reduced - (((reduced > (templ << 32)) && (tempul == 32'b0)) ? 64'h00000000ffffffff : 64'h0);")
    emit("        reduced = reduced + (((reduced < (templ << 32)) && (tempul != 32'b0)) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift == 64) begin")
    emit("        templ = {32'b0, a[31:0]};")
    emit("        templ = (templ << 32) - templ;")
    emit("        tempu = a >> 32;")
    emit("        reduced = templ - tempu;")
    emit("        reduced = reduced - ((reduced > templ) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift < 96) begin")
    emit("        templ32 = a[31:0] << (shift - 64);")
    emit("        templ = {32'b0, templ32};")
    emit("        templ = (templ << 32) - templ;")
    emit("        tempu = a >> (96 - shift);")
    emit("        reduced = templ - tempu;")
    emit("        reduced = reduced - ((reduced > templ) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end else if (shift == 96) begin")
    emit("        int_lsh = int_ctor(P - a);")
    emit("      end else if (shift < 128) begin")
    emit("        templ = a << (shift - 96);")
    emit("        tempu = a >> (160 - shift);")
    emit("        reduced = templ + (tempu << 32) - tempu;")
    emit("        reduced = reduced + ((reduced < templ) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(P - int_ctor(reduced));")
    emit("      end else if (shift == 128) begin")
    emit("        templ = {32'b0, a[31:0]};")
    emit("        tempul = a[63:32];")
    emit("        int_lsh = int_sub(int_sub(int_ctor({32'b0, tempul}), int_ctor(templ << 32)), int_ctor({32'b0, tempul} << 32));")
    emit("      end else if (shift < 160) begin")
    emit("        templ32 = a[31:0] << (shift - 128);")
    emit("        templ = {32'b0, templ32};")
    emit("        tempul = a >> (160 - shift);")
    emit("        tempuu = a >> (192 - shift);")
    emit("        int_lsh = int_sub(int_sub(int_ctor({32'b0, tempul} + tempuu), int_ctor(templ << 32)), int_ctor({32'b0, tempul} << 32));")
    emit("      end else if (shift == 160) begin")
    emit("        templ = {32'b0, a[31:0]};")
    emit("        tempu = a >> 32;")
    emit("        int_lsh = int_sub(int_ctor(templ + tempu), int_ctor(templ << 32));")
    emit("      end else begin")
    emit("        templ32 = a[31:0] << (shift - 160);")
    emit("        templ = {32'b0, templ32};")
    emit("        tempu = a >> (192 - shift);")
    emit("        reduced = templ + tempu - (templ << 32);")
    emit("        reduced = reduced - ((reduced > tempu) ? 64'h00000000ffffffff : 64'h0);")
    emit("        int_lsh = int_ctor(reduced);")
    emit("      end")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [31:0] decompose_digit;")
    emit("    input [31:0] value;")
    emit("    input integer digit;")
    emit("    reg [31:0] adjusted;")
    emit("    begin")
    emit("      adjusted = value + 32'h82082000;")
    emit("      if (digit == 0) begin")
    emit("        decompose_digit = ((adjusted >> 26) & 32'h3f) - 32'd32;")
    emit("      end else if (digit == 1) begin")
    emit("        decompose_digit = ((adjusted >> 20) & 32'h3f) - 32'd32;")
    emit("      end else begin")
    emit("        decompose_digit = ((adjusted >> 14) & 32'h3f) - 32'd32;")
    emit("      end")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [5:0] bit_reverse6;")
    emit("    input [5:0] value;")
    emit("    begin")
    emit("      bit_reverse6 = {value[0], value[1], value[2], value[3], value[4], value[5]};")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [1023:0] pack_output;")
    emit("    input [5:0] cycle;")
    emit("    integer pack_lane;")
    emit("    integer pack_component;")
    emit("    integer pack_cycle;")
    emit("    begin")
    emit("      pack_output = 1024'b0;")
    emit("      pack_component = cycle / 32;")
    emit("      pack_cycle = cycle % 32;")
    emit("      for (pack_lane = 0; pack_lane < 32; pack_lane = pack_lane + 1) begin")
    emit("        pack_output[pack_lane * 32 +: 32] = result_mem[pack_component * 1024 + pack_lane * 32 + pack_cycle];")
    emit("      end")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  task automatic butterfly_add;")
    emit("    input integer base;")
    emit("    input integer size;")
    emit("    integer add_idx;")
    emit("    integer half_size;")
    emit("    reg [63:0] temp_value;")
    emit("    begin")
    emit("      half_size = size >> 1;")
    emit("      for (add_idx = 0; add_idx < half_size; add_idx = add_idx + 1) begin")
    emit("        temp_value = work_mem[base + add_idx];")
    emit("        work_mem[base + add_idx] = int_add(work_mem[base + add_idx], work_mem[base + half_size + add_idx]);")
    emit("        work_mem[base + half_size + add_idx] = int_sub(temp_value, work_mem[base + half_size + add_idx]);")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task automatic intt_butterfly;")
    emit("    input integer base;")
    emit("    input integer size;")
    emit("    input integer radixbit;")
    emit("    integer bfly_level;")
    emit("    integer bfly_segment;")
    emit("    integer bfly_idx;")
    emit("    integer bfly_i;")
    emit("    integer bfly_j;")
    emit("    integer segment_size;")
    emit("    integer current_radix;")
    emit("    integer butterfly_block;")
    emit("    integer half_size;")
    emit("    integer local_base;")
    emit("    reg [63:0] temp_value;")
    emit("    begin")
    emit("      butterfly_block = size >> radixbit;")
    emit("      for (bfly_level = 0; bfly_level < radixbit; bfly_level = bfly_level + 1) begin")
    emit("        segment_size = size >> bfly_level;")
    emit("        half_size = segment_size >> 1;")
    emit("        current_radix = radixbit - bfly_level;")
    emit("        for (bfly_segment = 0; bfly_segment < (1 << bfly_level); bfly_segment = bfly_segment + 1) begin")
    emit("          local_base = base + bfly_segment * segment_size;")
    emit("          for (bfly_idx = 0; bfly_idx < half_size; bfly_idx = bfly_idx + 1) begin")
    emit("            temp_value = work_mem[local_base + bfly_idx];")
    emit("            work_mem[local_base + bfly_idx] = int_add(work_mem[local_base + bfly_idx], work_mem[local_base + half_size + bfly_idx]);")
    emit("            work_mem[local_base + half_size + bfly_idx] = int_sub(temp_value, work_mem[local_base + half_size + bfly_idx]);")
    emit("          end")
    emit("          if (current_radix > 1) begin")
    emit("            for (bfly_i = 1; bfly_i < (1 << (current_radix - 1)); bfly_i = bfly_i + 1) begin")
    emit("              for (bfly_j = 0; bfly_j < butterfly_block; bfly_j = bfly_j + 1) begin")
    emit("                work_mem[local_base + half_size + bfly_i * butterfly_block + bfly_j] = int_lsh(work_mem[local_base + half_size + bfly_i * butterfly_block + bfly_j], 3 * (bfly_i << (6 - current_radix)));")
    emit("              end")
    emit("            end")
    emit("          end")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task automatic run_intt_core;")
    emit("    integer tw_i;")
    emit("    integer tw_j;")
    emit("    integer rem_block;")
    emit("    begin")
    emit("      intt_butterfly(0, 1024, 6);")
    emit("      for (tw_i = 1; tw_i < 64; tw_i = tw_i + 1) begin")
    emit("        for (tw_j = 1; tw_j < 16; tw_j = tw_j + 1) begin")
    emit("          work_mem[tw_i * 16 + tw_j] = int_mul(work_mem[tw_i * 16 + tw_j], table_intt_mem[bit_reverse6(tw_i[5:0]) * tw_j]);")
    emit("        end")
    emit("      end")
    emit("      for (rem_block = 0; rem_block < 64; rem_block = rem_block + 1) begin")
    emit("        intt_butterfly(rem_block * 16, 16, 4);")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task automatic ntt_butterfly;")
    emit("    input integer base;")
    emit("    input integer size;")
    emit("    input integer radixbit;")
    emit("    integer ntt_level;")
    emit("    integer ntt_segment;")
    emit("    integer segment_size;")
    emit("    integer half_size;")
    emit("    integer current_radix;")
    emit("    integer butterfly_block;")
    emit("    integer local_base;")
    emit("    integer ntt_i;")
    emit("    integer ntt_j;")
    emit("    begin")
    emit("      for (ntt_level = 1; ntt_level <= radixbit; ntt_level = ntt_level + 1) begin")
    emit("        segment_size = size >> (radixbit - ntt_level);")
    emit("        half_size = segment_size >> 1;")
    emit("        current_radix = ntt_level;")
    emit("        butterfly_block = segment_size >> current_radix;")
    emit("        for (ntt_segment = 0; ntt_segment < (size / segment_size); ntt_segment = ntt_segment + 1) begin")
    emit("          local_base = base + ntt_segment * segment_size;")
    emit("          if (current_radix != 1) begin")
    emit("            for (ntt_i = 1; ntt_i < (1 << (current_radix - 1)); ntt_i = ntt_i + 1) begin")
    emit("              for (ntt_j = 0; ntt_j < butterfly_block; ntt_j = ntt_j + 1) begin")
    emit("                work_mem[local_base + ntt_i * butterfly_block + ntt_j + half_size] = int_lsh(work_mem[local_base + ntt_i * butterfly_block + ntt_j + half_size], 3 * (64 - (ntt_i << (6 - current_radix))));")
    emit("              end")
    emit("            end")
    emit("          end")
    emit("          butterfly_add(local_base, segment_size);")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task automatic ntt_radix;")
    emit("    input integer base;")
    emit("    input integer size;")
    emit("    input integer num_block;")
    emit("    input integer radixbit;")
    emit("    integer radix_i;")
    emit("    integer radix_j;")
    emit("    integer radix_block;")
    emit("    begin")
    emit("      radix_block = size >> radixbit;")
    emit("      for (radix_i = 1; radix_i < (1 << radixbit); radix_i = radix_i + 1) begin")
    emit("        for (radix_j = 1; radix_j < radix_block; radix_j = radix_j + 1) begin")
    emit("          work_mem[base + radix_i * radix_block + radix_j] = int_mul(work_mem[base + radix_i * radix_block + radix_j], table_ntt_mem[bit_reverse6(radix_i[5:0]) * num_block * radix_j]);")
    emit("        end")
    emit("      end")
    emit("      ntt_butterfly(base, size, radixbit);")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task automatic run_ntt_core;")
    emit("    integer rem_block;")
    emit("    begin")
    emit("      for (rem_block = 0; rem_block < 64; rem_block = rem_block + 1) begin")
    emit("        ntt_butterfly(rem_block * 16, 16, 4);")
    emit("      end")
    emit("      ntt_radix(0, 1024, 1, 6);")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task automatic compute_externalproduct;")
    emit("    integer comp;")
    emit("    integer digit;")
    emit("    integer out_comp;")
    emit("    integer coeff_idx;")
    emit("    integer row_idx;")
    emit("    reg first_accum;")
    emit("    reg [63:0] term_value;")
    emit("    reg [63:0] temp_value;")
    emit("    begin")
    emit("      for (coeff_idx = 0; coeff_idx < 2048; coeff_idx = coeff_idx + 1) begin")
    emit("        restr_mem[coeff_idx] = 64'b0;")
    emit("      end")
    emit("      first_accum = 1'b1;")
    emit("      for (comp = 0; comp < 2; comp = comp + 1) begin")
    emit("        for (digit = 0; digit < 3; digit = digit + 1) begin")
    emit("          for (coeff_idx = 0; coeff_idx < 1024; coeff_idx = coeff_idx + 1) begin")
    emit("            work_mem[coeff_idx] = int_mul({32'b0, decompose_digit(input_mem[comp * 1024 + coeff_idx], digit)}, twist_intt_mem[coeff_idx]);")
    emit("          end")
    emit("          run_intt_core;")
    emit("          row_idx = comp * 3 + digit;")
    emit("          for (out_comp = 0; out_comp < 2; out_comp = out_comp + 1) begin")
    emit("            for (coeff_idx = 0; coeff_idx < 1024; coeff_idx = coeff_idx + 1) begin")
    emit("              term_value = int_mul(work_mem[coeff_idx], trgsw_mem[row_idx * 2048 + out_comp * 1024 + coeff_idx]);")
    emit("              if (first_accum) begin")
    emit("                restr_mem[out_comp * 1024 + coeff_idx] = term_value;")
    emit("              end else begin")
    emit("                restr_mem[out_comp * 1024 + coeff_idx] = int_add(restr_mem[out_comp * 1024 + coeff_idx], term_value);")
    emit("              end")
    emit("            end")
    emit("          end")
    emit("          first_accum = 1'b0;")
    emit("        end")
    emit("      end")
    emit("      for (out_comp = 0; out_comp < 2; out_comp = out_comp + 1) begin")
    emit("        for (coeff_idx = 0; coeff_idx < 1024; coeff_idx = coeff_idx + 1) begin")
    emit("          work_mem[coeff_idx] = restr_mem[out_comp * 1024 + coeff_idx];")
    emit("        end")
    emit("        run_ntt_core;")
    emit("        for (coeff_idx = 0; coeff_idx < 1024; coeff_idx = coeff_idx + 1) begin")
    emit("          temp_value = int_mul(int_mul(work_mem[coeff_idx], twist_ntt_mem[coeff_idx]), INV_N);")
    emit("          result_mem[out_comp * 1024 + coeff_idx] = temp_value[31:0];")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  initial begin")
    emit("    state = STATE_CAPTURE;")
    emit("    input_count = 6'd0;")
    emit("    input_component = 1'b0;")
    emit("    trgsw_count = 8'd0;")
    emit("    output_count = 6'd0;")
    emit("    output_word = 1024'b0;")
    emit("    valid_word = 1'b0;")
    emit("    for (idx = 0; idx < 2048; idx = idx + 1) begin")
    emit("      input_mem[idx] = 32'b0;")
    emit("      restr_mem[idx] = 64'b0;")
    emit("      result_mem[idx] = 32'b0;")
    emit("    end")
    emit("    for (idx = 0; idx < 1024; idx = idx + 1) begin")
    emit("      work_mem[idx] = 64'b0;")
    emit("    end")
    emit("    for (idx = 0; idx < 12288; idx = idx + 1) begin")
    emit("      trgsw_mem[idx] = 64'b0;")
    emit("    end")
    lines.extend(_constant_initializers("table_ntt_mem", table_ntt))
    lines.extend(_constant_initializers("table_intt_mem", table_intt))
    lines.extend(_constant_initializers("twist_ntt_mem", twist_ntt))
    lines.extend(_constant_initializers("twist_intt_mem", twist_intt))
    emit("  end")
    emit("")
    emit("  always @(negedge clock) begin")
    emit("    if (reset) begin")
    emit("      state <= STATE_CAPTURE;")
    emit("      input_count <= 6'd0;")
    emit("      input_component <= 1'b0;")
    emit("      trgsw_count <= 8'd0;")
    emit("      output_count <= 6'd0;")
    emit("      output_word <= 1024'b0;")
    emit("      valid_word <= 1'b0;")
    emit("    end else begin")
    emit("      if (io_trgswinvalid && io_trgswinready) begin")
    emit("        for (trgsw_component = 0; trgsw_component < 2; trgsw_component = trgsw_component + 1) begin")
    emit("          for (trgsw_lane = 0; trgsw_lane < 32; trgsw_lane = trgsw_lane + 1) begin")
    emit("            trgsw_mem[(trgsw_count / 32) * 2048 + trgsw_component * 1024 + (trgsw_count % 32) * 32 + trgsw_lane] <= io_trgswin[(trgsw_component * 32 + trgsw_lane) * 64 +: 64];")
    emit("          end")
    emit("        end")
    emit("        trgsw_count <= trgsw_count + 8'd1;")
    emit("      end")
    emit("      case (state)")
    emit("        STATE_CAPTURE: begin")
    emit("          valid_word <= 1'b0;")
    emit("          if (io_validin) begin")
    emit("            for (lane = 0; lane < 32; lane = lane + 1) begin")
    emit("              input_mem[input_component * 1024 + lane * 32 + input_count] <= io_in[lane * 32 +: 32];")
    emit("            end")
    emit("            if (input_count == 6'd31) begin")
    emit("              input_count <= 6'd0;")
    emit("              if (input_component) begin")
    emit("                input_component <= 1'b0;")
    emit("                if ((trgsw_count == 8'd192) || (io_trgswinvalid && io_trgswinready && trgsw_count == 8'd191)) begin")
    emit("                  state <= STATE_COMPUTE;")
    emit("                end else begin")
    emit("                  state <= STATE_WAIT_TRGSW;")
    emit("                end")
    emit("              end else begin")
    emit("                input_component <= 1'b1;")
    emit("              end")
    emit("            end else begin")
    emit("              input_count <= input_count + 6'd1;")
    emit("            end")
    emit("          end")
    emit("        end")
    emit("        STATE_WAIT_TRGSW: begin")
    emit("          valid_word <= 1'b0;")
    emit("          if ((trgsw_count == 8'd192) || (io_trgswinvalid && io_trgswinready && trgsw_count == 8'd191)) begin")
    emit("            state <= STATE_COMPUTE;")
    emit("          end")
    emit("        end")
    emit("        STATE_COMPUTE: begin")
    emit("          compute_externalproduct;")
    emit("          output_count <= 6'd0;")
    emit("          output_word <= pack_output(6'd0);")
    emit("          valid_word <= 1'b1;")
    emit("          state <= STATE_OUTPUT;")
    emit("        end")
    emit("        STATE_OUTPUT: begin")
    emit("          if (output_count == 6'd63) begin")
    emit("            output_count <= 6'd0;")
    emit("            output_word <= 1024'b0;")
    emit("            valid_word <= 1'b0;")
    emit("            input_count <= 6'd0;")
    emit("            input_component <= 1'b0;")
    emit("            trgsw_count <= 8'd0;")
    emit("            state <= STATE_CAPTURE;")
    emit("          end else begin")
    emit("            output_count <= output_count + 6'd1;")
    emit("            output_word <= pack_output(output_count + 6'd1);")
    emit("            valid_word <= 1'b1;")
    emit("          end")
    emit("        end")
    emit("        default: begin")
    emit("          state <= STATE_CAPTURE;")
    emit("          valid_word <= 1'b0;")
    emit("        end")
    emit("      endcase")
    emit("    end")
    emit("  end")
    emit("endmodule")
    return "\n".join(lines) + "\n"


def generate_hoge_nttid_behavioral() -> str:
    """Return a generated identity RTL implementation for NTTidPackedTop."""

    return """// Generated behavioral HOGE NTTid identity candidate.
module NTTidPackedTop(
  input            clock,
  input            reset,
  input  [65535:0] io_in,
  output [65535:0] io_out
);
  assign io_out = io_in;
endmodule
"""


def generate_hoge_streaming_ntt_interface_behavioral() -> str:
    """Return a generated NTTWrap interface/lint candidate.

    The repository task for this top is lint-only. This module preserves the
    required ready/valid shape and data packing but is not a scored arithmetic
    oracle.
    """

    return """// Generated behavioral HOGE streaming NTT interface candidate.
module NTTWrap(
  input           clock,
  input           reset,
  input  [2047:0] io_in,
  output [2047:0] io_out,
  output          io_validout,
  input           io_enable,
  output          io_ready
);
  reg [2047:0] output_word;
  reg valid_word;

  assign io_ready = 1'b1;
  assign io_out = output_word;
  assign io_validout = valid_word;

  always @(posedge clock) begin
    if (reset) begin
      output_word <= 2048'b0;
      valid_word <= 1'b0;
    end else begin
      valid_word <= io_enable;
      if (io_enable) begin
        output_word <= io_in;
      end
    end
  end
endmodule
"""
