"""Deterministic behavioral RTL generator for the YATA RAINTT task."""

from __future__ import annotations


WORD_BITS = 27
NBIT = 9
N = 1 << NBIT
LANES = 64
CYCLES = N // LANES
MASK27 = (1 << WORD_BITS) - 1
K_SMALL = 5
K = K_SMALL**4
SHIFT_AMOUNT = 16
SHIFT_VAL = 1 << SHIFT_AMOUNT
P = (K << SHIFT_AMOUNT) + 1
R = (1 << WORD_BITS) % P
R2 = (R * R) % P
RADIXBIT = 3
RADIXS2 = 1 << (RADIXBIT - 1)


def _u27(value: int) -> int:
    return value & MASK27


def _s27(value: int) -> int:
    value &= MASK27
    return value - (1 << WORD_BITS) if value & (1 << (WORD_BITS - 1)) else value


def _s54(value: int) -> int:
    value &= (1 << 54) - 1
    return value - (1 << 54) if value & (1 << 53) else value


def _redc(value: int) -> int:
    value &= (1 << 54) - 1
    low = value & MASK27
    m = (((_u27(low * K) << SHIFT_AMOUNT) - low) & MASK27)
    t = (value + ((m * K) << SHIFT_AMOUNT) + m) >> WORD_BITS
    t = _u27(t)
    return _u27(t - P if t > P else t)


def _sredc(value: int) -> int:
    value = _s54(value)
    a0 = _u27(value)
    a1 = _s27(value >> WORD_BITS)
    m = _s27(-((a0 * K) * SHIFT_VAL) + a0)
    t1 = _s54((_s54(m) * K) << SHIFT_AMOUNT)
    t1 = _s54(t1 + m)
    t1 = _s27(t1 >> WORD_BITS)
    return _s27(a1 - t1)


def _mul_redc(a: int, b: int) -> int:
    return _redc(_u27(a) * _u27(b))


def _mul_sredc(a: int, b: int) -> int:
    return _sredc(_s27(a) * _s27(b))


def _pow_redc(a: int, exponent: int) -> int:
    result = 1
    a_r = _mul_redc(R2, a)
    for _ in range(exponent):
        result = _mul_redc(result, a_r)
    return result


W = _pow_redc(31, K)


def _bit_reverse(value: int, bits: int) -> int:
    if bits <= 1:
        return value
    center = value & ((bits & 1) << (bits // 2))
    return (
        _bit_reverse(value & ((1 << (bits // 2)) - 1), bits // 2)
        << ((bits + 1) // 2)
    ) | center | _bit_reverse(value >> ((bits + 1) // 2), bits // 2)


def _table_gen() -> list[list[list[int]]]:
    table = [[[0 for _ in range(N)] for _ in range(2)] for _ in range(2)]
    w = _pow_redc(W, 1 << (SHIFT_AMOUNT - NBIT))
    w_r = _mul_redc(w, R2)
    table[0][0][0] = table[1][0][0] = R
    table[0][1][0] = table[1][1][0] = R2
    for index in range(1, N):
        table[1][0][index] = _mul_redc(table[1][0][index - 1], w_r)
        table[1][1][index] = _mul_redc(table[1][0][index], R2)
    for variant in range(2):
        for index in range(1, N):
            table[0][variant][index] = table[1][variant][N - index]
    return table


def _twist_gen() -> list[list[int]]:
    twist = [[0 for _ in range(N)] for _ in range(2)]
    inv_n = pow(N, -1, P)
    w_r = _mul_redc(_pow_redc(W, 1 << (SHIFT_AMOUNT - NBIT - 1)), R2)
    twist[1][0] = R
    for index in range(1, N):
        twist[1][index] = _mul_redc(twist[1][index - 1], w_r)
    twist[0][N - 1] = _mul_redc(_mul_redc(twist[1][N - 1], w_r), (inv_n * w_r) % P)
    twist[0][0] = (inv_n * R) % P
    for index in range(2, N):
        twist[0][N - index] = _mul_redc(twist[0][N - index + 1], w_r)
    for index in range(N):
        if ((index >> (NBIT - RADIXBIT)) & ((1 << (RADIXBIT - 1)) - 1)) != 0:
            twist[0][index] = _mul_redc(twist[0][index], R2)
    return twist


def _sconst(value: int) -> str:
    return f"64'sd{value}"


def _emit(lines: list[str], text: str = "") -> None:
    lines.append(text)


def _port_lines(prefix: str, direction: str, width: str) -> list[str]:
    return [f"  {direction} {width} {prefix}_{lane}," for lane in range(LANES)]


def _assign_lane_outputs(
    lines: list[str],
    prefix: str,
    mem: str,
    stride_expr: str,
    value_suffix: str = "",
) -> None:
    for lane in range(LANES):
        _emit(
            lines,
            f"  assign {prefix}_{lane} = "
            f"{mem}[{stride_expr.format(lane=lane, lane_times_cycles=lane * CYCLES)}]"
            f"{value_suffix};",
        )


def _capture_lanes(lines: list[str], prefix: str, mem: str, index_expr: str, cast: str) -> None:
    for lane in range(LANES):
        _emit(
            lines,
            f"              {mem}[{index_expr.format(lane=lane, lane_times_cycles=lane * CYCLES)}] <= "
            f"{cast.format(port=f'{prefix}_{lane}')};",
        )


def _constant_initializers(lines: list[str], name: str, values: list[int]) -> None:
    for index, value in enumerate(values):
        _emit(lines, f"    {name}[{index}] = {_sconst(value)};")


def generate_yata_raintt_behavioral() -> str:
    """Return generated behavioral RTL for the YATA RAINTT INTT/NTT task."""

    table = _table_gen()
    twist = _twist_gen()
    lines: list[str] = []
    emit = lambda text="": _emit(lines, text)

    emit("/* verilator lint_off WIDTH */")
    emit("// Generated behavioral YATA RAINTT candidate.")
    emit("module YataRainttTop(")
    emit("  input         clock,")
    emit("  input         reset,")
    lines.extend(_port_lines("io_intt_in", "input", " [31:0]"))
    emit("  input         io_intt_validin,")
    lines.extend(_port_lines("io_intt_out", "output", "[26:0]"))
    emit("  output        io_intt_validout,")
    lines.extend(_port_lines("io_ntt_in", "input", " [26:0]"))
    emit("  input         io_ntt_validin,")
    for line in _port_lines("io_ntt_out", "output", "[31:0]"):
        emit(line)
    emit("  output        io_ntt_validout")
    emit(");")
    emit("  localparam signed [63:0] P = 64'sd40960001;")
    emit("  localparam signed [63:0] R2 = 64'sd15277344;")
    emit("  localparam [1:0] STATE_CAPTURE = 2'd0;")
    emit("  localparam [1:0] STATE_COMPUTE = 2'd1;")
    emit("  localparam [1:0] STATE_OUTPUT = 2'd2;")
    emit("")
    emit("  reg [1:0] intt_state;")
    emit("  reg [1:0] ntt_state;")
    emit("  reg [3:0] intt_input_count;")
    emit("  reg [3:0] intt_output_count;")
    emit("  reg [3:0] ntt_input_count;")
    emit("  reg [3:0] ntt_output_count;")
    emit("  reg intt_valid_word;")
    emit("  reg ntt_valid_word;")
    emit("  reg signed [63:0] intt_input_mem [0:511];")
    emit("  reg signed [63:0] ntt_input_mem [0:511];")
    emit("  reg signed [63:0] work_mem [0:511];")
    emit("  reg signed [63:0] intt_output_mem [0:511];")
    emit("  reg [31:0] ntt_output_mem [0:511];")
    emit("  reg signed [63:0] table_intt_0 [0:511];")
    emit("  reg signed [63:0] table_intt_1 [0:511];")
    emit("  reg signed [63:0] table_ntt_0 [0:511];")
    emit("  reg signed [63:0] table_ntt_1 [0:511];")
    emit("  reg signed [63:0] twist_intt [0:511];")
    emit("  reg signed [63:0] twist_ntt [0:511];")
    emit("  integer idx;")
    emit("  integer lane;")
    emit("")
    emit("  assign io_intt_validout = intt_valid_word;")
    emit("  assign io_ntt_validout = ntt_valid_word;")
    _assign_lane_outputs(
        lines,
        "io_intt_out",
        "intt_output_mem",
        "({{28'b0, intt_output_count}} * 32'd64) + 32'd{lane}",
        "[26:0]",
    )
    _assign_lane_outputs(
        lines,
        "io_ntt_out",
        "ntt_output_mem",
        "32'd{lane_times_cycles} + {{28'b0, ntt_output_count}}",
    )
    emit("")
    emit("  function signed [63:0] cast_s27;")
    emit("    input signed [127:0] value;")
    emit("    reg [26:0] low;")
    emit("    begin")
    emit("      low = value[26:0];")
    emit("      cast_s27 = {{37{low[26]}}, low};")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] cast_s54;")
    emit("    input signed [127:0] value;")
    emit("    reg [53:0] low;")
    emit("    begin")
    emit("      low = value[53:0];")
    emit("      cast_s54 = {{10{low[53]}}, low};")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] sign_extend_27;")
    emit("    input [26:0] value;")
    emit("    begin")
    emit("      sign_extend_27 = {{37{value[26]}}, value};")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] add_mod;")
    emit("    input signed [63:0] a;")
    emit("    input signed [63:0] b;")
    emit("    reg signed [63:0] sum;")
    emit("    begin")
    emit("      sum = cast_s54(a + b);")
    emit("      if (sum >= P) add_mod = cast_s27(sum - P);")
    emit("      else if (sum <= -P) add_mod = cast_s27(sum + P);")
    emit("      else add_mod = cast_s27(sum);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] sub_mod;")
    emit("    input signed [63:0] a;")
    emit("    input signed [63:0] b;")
    emit("    reg signed [63:0] diff;")
    emit("    begin")
    emit("      diff = cast_s54(a - b);")
    emit("      if (diff >= P) sub_mod = cast_s27(diff - P);")
    emit("      else if (diff <= -P) sub_mod = cast_s27(diff + P);")
    emit("      else sub_mod = cast_s27(diff);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] sredc;")
    emit("    input signed [63:0] a;")
    emit("    reg [26:0] a0;")
    emit("    reg signed [63:0] a1;")
    emit("    reg signed [63:0] m;")
    emit("    reg signed [63:0] t1;")
    emit("    begin")
    emit("      a0 = a[26:0];")
    emit("      a1 = cast_s27(cast_s54(a) >>> 27);")
    emit("      m = cast_s27(-(128'sd625 * 128'sd65536 * {101'b0, a0}) + {101'b0, a0});")
    emit("      t1 = cast_s54(cast_s54(m) * 128'sd625);")
    emit("      t1 = cast_s54(t1 <<< 16);")
    emit("      t1 = cast_s54(t1 + m);")
    emit("      t1 = cast_s27(t1 >>> 27);")
    emit("      sredc = cast_s27(a1 - t1);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] mul_sredc;")
    emit("    input signed [63:0] a;")
    emit("    input signed [63:0] b;")
    emit("    begin")
    emit("      mul_sredc = sredc(cast_s27(a) * cast_s27(b));")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function signed [63:0] const_twiddle;")
    emit("    input signed [63:0] value;")
    emit("    input integer radix_bits;")
    emit("    input integer number;")
    emit("    reg signed [63:0] factor;")
    emit("    begin")
    emit("      factor = 64'sd1;")
    emit("      if (radix_bits == 2 && number == 1) factor = 64'sd6400;")
    emit("      else if (radix_bits == 3 && number == 1) factor = 64'sd80;")
    emit("      else if (radix_bits == 3 && number == 2) factor = 64'sd6400;")
    emit("      else if (radix_bits == 3 && number == 3) factor = 64'sd512000;")
    emit("      const_twiddle = cast_s54(cast_s54(value) * factor);")
    emit("    end")
    emit("  endfunction")
    emit("")
    emit("  function [2:0] bit_reverse3;")
    emit("    input [2:0] value;")
    emit("    begin")
    emit("      bit_reverse3 = {value[0], value[1], value[2]};")
    emit("    end")
    emit("  endfunction")
    emit("")

    _emit_yata_tasks(lines)

    emit("  initial begin")
    emit("    intt_state = STATE_CAPTURE;")
    emit("    ntt_state = STATE_CAPTURE;")
    emit("    intt_input_count = 4'd0;")
    emit("    intt_output_count = 4'd0;")
    emit("    ntt_input_count = 4'd0;")
    emit("    ntt_output_count = 4'd0;")
    emit("    intt_valid_word = 1'b0;")
    emit("    ntt_valid_word = 1'b0;")
    emit("    for (idx = 0; idx < 512; idx = idx + 1) begin")
    emit("      intt_input_mem[idx] = 64'sd0;")
    emit("      ntt_input_mem[idx] = 64'sd0;")
    emit("      work_mem[idx] = 64'sd0;")
    emit("      intt_output_mem[idx] = 64'sd0;")
    emit("      ntt_output_mem[idx] = 32'd0;")
    emit("    end")
    _constant_initializers(lines, "table_intt_0", table[1][0])
    _constant_initializers(lines, "table_intt_1", table[1][1])
    _constant_initializers(lines, "table_ntt_0", table[0][0])
    _constant_initializers(lines, "table_ntt_1", table[0][1])
    _constant_initializers(lines, "twist_intt", twist[1])
    _constant_initializers(lines, "twist_ntt", twist[0])
    emit("  end")
    emit("")
    _emit_state_machine(lines)
    emit("endmodule")
    emit("/* verilator lint_on WIDTH */")
    return "\n".join(lines) + "\n"


def _emit_yata_tasks(lines: list[str]) -> None:
    emit = lambda text="": _emit(lines, text)
    emit("  task butterfly_add_both_mod;")
    emit("    input integer base; input integer size;")
    emit("    integer b_idx; reg signed [63:0] temp;")
    emit("    begin")
    emit("      for (b_idx = 0; b_idx < size / 2; b_idx = b_idx + 1) begin")
    emit("        temp = cast_s27(work_mem[base + b_idx]);")
    emit("        work_mem[base + b_idx] = add_mod(work_mem[base + b_idx], work_mem[base + b_idx + size / 2]);")
    emit("        work_mem[base + b_idx + size / 2] = sub_mod(temp, work_mem[base + b_idx + size / 2]);")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task butterfly_add_add_mod;")
    emit("    input integer base; input integer size;")
    emit("    integer b_idx; reg signed [63:0] temp;")
    emit("    begin")
    emit("      for (b_idx = 0; b_idx < size / 2; b_idx = b_idx + 1) begin")
    emit("        temp = cast_s27(work_mem[base + b_idx]);")
    emit("        work_mem[base + b_idx] = add_mod(work_mem[base + b_idx], work_mem[base + b_idx + size / 2]);")
    emit("        work_mem[base + b_idx + size / 2] = cast_s54(temp - work_mem[base + b_idx + size / 2]);")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task butterfly_add_both_sredc;")
    emit("    input integer base; input integer size;")
    emit("    integer b_idx; reg signed [63:0] temp;")
    emit("    begin")
    emit("      for (b_idx = 0; b_idx < size / 2; b_idx = b_idx + 1) begin")
    emit("        temp = cast_s54(work_mem[base + b_idx]);")
    emit("        work_mem[base + b_idx] = sredc(cast_s54(work_mem[base + b_idx] + work_mem[base + b_idx + size / 2]));")
    emit("        work_mem[base + b_idx + size / 2] = sredc(cast_s54(temp - work_mem[base + b_idx + size / 2]));")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task intt_butterfly1; input integer base; input integer size; begin butterfly_add_both_mod(base, size); end endtask")
    emit("")
    emit("  task intt_butterfly2;")
    emit("    input integer base; input integer size;")
    emit("    integer block; integer i; integer j; integer target;")
    emit("    begin")
    emit("      butterfly_add_add_mod(base, size);")
    emit("      intt_butterfly1(base, size / 2);")
    emit("      block = size >> 2;")
    emit("      for (i = 1; i < 2; i = i + 1) begin")
    emit("        for (j = 0; j < block; j = j + 1) begin")
    emit("          target = base + i * block + j + size / 2;")
    emit("          work_mem[target] = const_twiddle(work_mem[target], 2, 1);")
    emit("        end")
    emit("      end")
    emit("      butterfly_add_both_sredc(base + size / 2, size / 2);")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task intt_butterfly3;")
    emit("    input integer base; input integer size;")
    emit("    integer block; integer i; integer idx_a; integer idx_b;")
    emit("    reg signed [63:0] temp;")
    emit("    begin")
    emit("      butterfly_add_add_mod(base, size);")
    emit("      intt_butterfly2(base, size / 2);")
    emit("      block = size >> 3;")
    emit("      for (i = 0; i < block; i = i + 1) begin")
    emit("        idx_a = base + i + size / 2; idx_b = base + 2 * block + i + size / 2;")
    emit("        work_mem[idx_b] = const_twiddle(work_mem[idx_b], 3, 2);")
    emit("        temp = cast_s54(work_mem[idx_a]);")
    emit("        work_mem[idx_a] = cast_s54(work_mem[idx_a] + work_mem[idx_b]);")
    emit("        work_mem[idx_b] = cast_s54(temp - work_mem[idx_b]);")
    emit("      end")
    emit("      for (i = 0; i < block; i = i + 1) begin")
    emit("        idx_a = base + block + i + size / 2; idx_b = base + 3 * block + i + size / 2;")
    emit("        temp = const_twiddle(work_mem[idx_a], 3, 3);")
    emit("        work_mem[idx_a] = cast_s54(const_twiddle(work_mem[idx_a], 3, 1) + const_twiddle(work_mem[idx_b], 3, 3));")
    emit("        work_mem[idx_b] = cast_s54(temp + const_twiddle(work_mem[idx_b], 3, 1));")
    emit("      end")
    emit("      butterfly_add_both_sredc(base + size / 2, size / 4);")
    emit("      butterfly_add_both_sredc(base + 3 * size / 4, size / 4);")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task intt_radix;")
    emit("    input integer base; input integer size; input integer num_block;")
    emit("    integer i; integer j; integer local_base; integer local_size; integer stride;")
    emit("    begin")
    emit("      intt_butterfly3(base, size);")
    emit("      local_size = size >> 3;")
    emit("      for (i = 1; i < 8; i = i + 1) begin")
    emit("        local_base = base + i * local_size;")
    emit("        stride = bit_reverse3(i[2:0]) * num_block;")
    emit("        for (j = 0; j < local_size; j = j + 1) begin")
    emit("          work_mem[local_base + j] = mul_sredc(work_mem[local_base + j], (i > 1) ? table_intt_1[stride * j] : table_intt_0[stride * j]);")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task compute_intt;")
    emit("    integer i; integer block;")
    emit("    begin")
    emit("      for (i = 0; i < 512; i = i + 1) work_mem[i] = mul_sredc(intt_input_mem[i], twist_intt[i]);")
    emit("      intt_radix(0, 512, 1);")
    emit("      for (block = 0; block < 8; block = block + 1) intt_radix(block * 64, 64, 8);")
    emit("      for (block = 0; block < 64; block = block + 1) intt_butterfly3(block * 8, 8);")
    emit("      for (i = 0; i < 512; i = i + 1) intt_output_mem[i] = work_mem[i];")
    emit("    end")
    emit("  endtask")
    emit("")
    _emit_ntt_tasks(lines)


def _emit_ntt_tasks(lines: list[str]) -> None:
    emit = lambda text="": _emit(lines, text)
    emit("  task ntt_butterfly1; input integer base; input integer size; begin butterfly_add_both_mod(base, size); end endtask")
    emit("")
    emit("  task ntt_butterfly2;")
    emit("    input integer base; input integer size; input integer do_redc;")
    emit("    integer index; reg signed [63:0] temp;")
    emit("    begin")
    emit("      ntt_butterfly1(base, size / 2);")
    emit("      ntt_butterfly1(base + size / 2, size / 2);")
    emit("      for (index = 0; index < size / 4; index = index + 1) begin")
    emit("        temp = cast_s27(work_mem[base + index]);")
    emit("        work_mem[base + index] = add_mod(work_mem[base + index], work_mem[base + index + size / 2]);")
    emit("        work_mem[base + index + size / 2] = sub_mod(temp, work_mem[base + index + size / 2]);")
    emit("      end")
    emit("      for (index = size / 4; index < size / 2; index = index + 1) begin")
    emit("        temp = cast_s54(work_mem[base + index]);")
    emit("        work_mem[base + index + size / 2] = cast_s54(-const_twiddle(work_mem[base + index + size / 2], 2, 1));")
    emit("        if (do_redc != 0) begin")
    emit("          work_mem[base + index] = sredc(cast_s54(work_mem[base + index] + work_mem[base + index + size / 2]));")
    emit("          work_mem[base + index + size / 2] = sredc(cast_s54(temp - work_mem[base + index + size / 2]));")
    emit("        end else begin")
    emit("          work_mem[base + index] = cast_s54(work_mem[base + index] + work_mem[base + index + size / 2]);")
    emit("          work_mem[base + index + size / 2] = cast_s54(temp - work_mem[base + index + size / 2]);")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task ntt_butterfly3;")
    emit("    input integer base; input integer size;")
    emit("    integer block; integer index; integer i; reg signed [63:0] temp;")
    emit("    begin")
    emit("      ntt_butterfly2(base, size / 2, 0);")
    emit("      ntt_butterfly1(base + 2 * size / 4, size / 4);")
    emit("      ntt_butterfly1(base + 3 * size / 4, size / 4);")
    emit("      block = size >> 3;")
    emit("      for (index = size / 2; index < size / 2 + block; index = index + 1) begin")
    emit("        temp = cast_s54(work_mem[base + index]);")
    emit("        work_mem[base + index] = add_mod(work_mem[base + index], work_mem[base + index + size / 4]);")
    emit("        work_mem[base + index + size / 4] = cast_s54(-const_twiddle(cast_s54(temp - work_mem[base + index + size / 4]), 3, 2));")
    emit("      end")
    emit("      for (index = size / 2 + block; index < size / 2 + 2 * block; index = index + 1) begin")
    emit("        temp = cast_s54(-const_twiddle(work_mem[base + index], 3, 1));")
    emit("        work_mem[base + index] = cast_s54(-const_twiddle(work_mem[base + index], 3, 3) - const_twiddle(work_mem[base + index + size / 4], 3, 1));")
    emit("        work_mem[base + index + size / 4] = cast_s54(temp - const_twiddle(work_mem[base + index + size / 4], 3, 3));")
    emit("      end")
    emit("      for (index = 0; index < block; index = index + 1) begin")
    emit("        temp = cast_s27(work_mem[base + index]);")
    emit("        work_mem[base + index] = add_mod(work_mem[base + index], work_mem[base + index + size / 2]);")
    emit("        work_mem[base + index + size / 2] = sub_mod(temp, work_mem[base + index + size / 2]);")
    emit("      end")
    emit("      for (i = 1; i < 4; i = i + 1) begin")
    emit("        for (index = i * block; index < (i + 1) * block; index = index + 1) begin")
    emit("          temp = cast_s54(work_mem[base + index]);")
    emit("          work_mem[base + index] = sredc(cast_s54(work_mem[base + index] + work_mem[base + index + size / 2]));")
    emit("          work_mem[base + index + size / 2] = sredc(cast_s54(temp - work_mem[base + index + size / 2]));")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task ntt_twiddle_mul;")
    emit("    input integer base; input integer sizebit; input integer stride;")
    emit("    integer index; integer size; integer flag;")
    emit("    begin")
    emit("      size = 1 << sizebit;")
    emit("      if (stride == 0) begin")
    emit("        for (index = 0; index < size; index = index + 1) begin")
    emit("          flag = (index >> (sizebit - 3)) & 3;")
    emit("          if (flag != 0) work_mem[base + index] = mul_sredc(work_mem[base + index], R2);")
    emit("        end")
    emit("      end else begin")
    emit("        for (index = 0; index < size; index = index + 1) begin")
    emit("          flag = (index >> (sizebit - 3)) & 3;")
    emit("          work_mem[base + index] = mul_sredc(work_mem[base + index], (flag != 0) ? table_ntt_1[stride * index] : table_ntt_0[stride * index]);")
    emit("        end")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task ntt_radix;")
    emit("    input integer base; input integer sizebit; input integer num_block;")
    emit("    integer i; integer size; integer local_size; integer stride;")
    emit("    begin")
    emit("      size = 1 << sizebit; local_size = size >> 3;")
    emit("      for (i = 0; i < 8; i = i + 1) begin")
    emit("        stride = bit_reverse3(i[2:0]) * num_block;")
    emit("        ntt_twiddle_mul(base + i * local_size, sizebit - 3, stride);")
    emit("      end")
    emit("      ntt_butterfly3(base, size);")
    emit("    end")
    emit("  endtask")
    emit("")
    emit("  task compute_ntt;")
    emit("    integer i; integer block; reg signed [63:0] mulres; reg signed [63:0] positive;")
    emit("    begin")
    emit("      for (i = 0; i < 512; i = i + 1) work_mem[i] = ntt_input_mem[i];")
    emit("      for (block = 0; block < 64; block = block + 1) ntt_butterfly3(block * 8, 8);")
    emit("      for (block = 0; block < 8; block = block + 1) ntt_radix(block * 64, 6, 8);")
    emit("      ntt_radix(0, 9, 1);")
    emit("      for (i = 0; i < 512; i = i + 1) begin")
    emit("        mulres = mul_sredc(work_mem[i], twist_ntt[i]);")
    emit("        positive = (mulres < 0) ? (mulres + P) : mulres;")
    emit("        ntt_output_mem[i] = ((positive * 64'sd7036874245) + 64'sd33554432) >>> 26;")
    emit("      end")
    emit("    end")
    emit("  endtask")
    emit("")


def _emit_state_machine(lines: list[str]) -> None:
    emit = lambda text="": _emit(lines, text)
    emit("  always @(posedge clock) begin")
    emit("    if (reset) begin")
    emit("      intt_state <= STATE_CAPTURE;")
    emit("      ntt_state <= STATE_CAPTURE;")
    emit("      intt_input_count <= 4'd0;")
    emit("      intt_output_count <= 4'd0;")
    emit("      ntt_input_count <= 4'd0;")
    emit("      ntt_output_count <= 4'd0;")
    emit("      intt_valid_word <= 1'b0;")
    emit("      ntt_valid_word <= 1'b0;")
    emit("    end else begin")
    emit("      case (intt_state)")
    emit("        STATE_CAPTURE: begin")
    emit("          intt_valid_word <= 1'b0;")
    emit("          if (io_intt_validin) begin")
    _capture_lanes(
        lines,
        "io_intt_in",
        "intt_input_mem",
        "32'd{lane_times_cycles} + {{28'b0, intt_input_count}}",
        "{{32'b0, {port}}}",
    )
    emit("            if (intt_input_count == 4'd7) begin intt_input_count <= 4'd0; intt_state <= STATE_COMPUTE; end")
    emit("            else intt_input_count <= intt_input_count + 4'd1;")
    emit("          end")
    emit("        end")
    emit("        STATE_COMPUTE: begin")
    emit("          compute_intt;")
    emit("          intt_output_count <= 4'd0;")
    emit("          intt_valid_word <= 1'b1;")
    emit("          intt_state <= STATE_OUTPUT;")
    emit("        end")
    emit("        STATE_OUTPUT: begin")
    emit("          if (intt_output_count == 4'd7) begin intt_output_count <= 4'd0; intt_valid_word <= 1'b0; intt_state <= STATE_CAPTURE; end")
    emit("          else begin intt_output_count <= intt_output_count + 4'd1; intt_valid_word <= 1'b1; end")
    emit("        end")
    emit("        default: begin")
    emit("          intt_state <= STATE_CAPTURE;")
    emit("          intt_valid_word <= 1'b0;")
    emit("          intt_input_count <= 4'd0;")
    emit("          intt_output_count <= 4'd0;")
    emit("        end")
    emit("      endcase")
    emit("")
    emit("      case (ntt_state)")
    emit("        STATE_CAPTURE: begin")
    emit("          ntt_valid_word <= 1'b0;")
    emit("          if (io_ntt_validin) begin")
    _capture_lanes(
        lines,
        "io_ntt_in",
        "ntt_input_mem",
        "({{28'b0, ntt_input_count}} * 32'd64) + 32'd{lane}",
        "sign_extend_27({port})",
    )
    emit("            if (ntt_input_count == 4'd7) begin ntt_input_count <= 4'd0; ntt_state <= STATE_COMPUTE; end")
    emit("            else ntt_input_count <= ntt_input_count + 4'd1;")
    emit("          end")
    emit("        end")
    emit("        STATE_COMPUTE: begin")
    emit("          compute_ntt;")
    emit("          ntt_output_count <= 4'd0;")
    emit("          ntt_valid_word <= 1'b1;")
    emit("          ntt_state <= STATE_OUTPUT;")
    emit("        end")
    emit("        STATE_OUTPUT: begin")
    emit("          if (ntt_output_count == 4'd7) begin ntt_output_count <= 4'd0; ntt_valid_word <= 1'b0; ntt_state <= STATE_CAPTURE; end")
    emit("          else begin ntt_output_count <= ntt_output_count + 4'd1; ntt_valid_word <= 1'b1; end")
    emit("        end")
    emit("        default: begin")
    emit("          ntt_state <= STATE_CAPTURE;")
    emit("          ntt_valid_word <= 1'b0;")
    emit("          ntt_input_count <= 4'd0;")
    emit("          ntt_output_count <= 4'd0;")
    emit("        end")
    emit("      endcase")
    emit("    end")
    emit("  end")
