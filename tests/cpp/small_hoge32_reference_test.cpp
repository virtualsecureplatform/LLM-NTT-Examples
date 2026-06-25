#include <verilated.h>
#include <VSmallHoge32P64Rtl.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <random>

#include "cuhe++.hpp"

namespace {
constexpr int kNbit = 5;
constexpr int kN = 1 << kNbit;
constexpr int kTests = 3;

#define SMALL_HOGE_FOR_EACH_LANE(X) \
    X(0) X(1) X(2) X(3) X(4) X(5) X(6) X(7) \
    X(8) X(9) X(10) X(11) X(12) X(13) X(14) X(15) \
    X(16) X(17) X(18) X(19) X(20) X(21) X(22) X(23) \
    X(24) X(25) X(26) X(27) X(28) X(29) X(30) X(31)

void tick(VSmallHoge32P64Rtl &dut)
{
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.clock = 0;
    dut.eval();
}

IData &intt_in(VSmallHoge32P64Rtl &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_intt_in_##n;
        SMALL_HOGE_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

QData &ntt_in(VSmallHoge32P64Rtl &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_ntt_in_##n;
        SMALL_HOGE_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

QData intt_out(const VSmallHoge32P64Rtl &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_intt_out_##n;
        SMALL_HOGE_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData ntt_out(const VSmallHoge32P64Rtl &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_ntt_out_##n;
        SMALL_HOGE_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

void reset(VSmallHoge32P64Rtl &dut)
{
    dut.reset = 1;
    dut.io_intt_validin = 0;
    dut.io_ntt_validin = 0;
    for (int i = 0; i < kN; ++i) {
        intt_in(dut, i) = 0;
        ntt_in(dut, i) = 0;
    }
    tick(dut);
    tick(dut);
    dut.reset = 0;
}

bool run_intt(VSmallHoge32P64Rtl &dut, const std::array<uint32_t, kN> &input,
              std::array<uint64_t, kN> &output, int &wait_cycles)
{
    for (int lane = 0; lane < kN; ++lane) intt_in(dut, lane) = input[lane];
    dut.io_intt_validin = 1;
    tick(dut);
    dut.io_intt_validin = 0;

    int watchdog = 0;
    while (!dut.io_intt_validout) {
        tick(dut);
        if (++watchdog > 200) {
            std::cerr << "small HOGE INTT validout timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;
    for (int lane = 0; lane < kN; ++lane) output[lane] = intt_out(dut, lane);
    tick(dut);
    return true;
}

bool run_ntt(VSmallHoge32P64Rtl &dut, const std::array<uint64_t, kN> &input,
             std::array<uint32_t, kN> &output, int &wait_cycles)
{
    for (int lane = 0; lane < kN; ++lane) ntt_in(dut, lane) = input[lane];
    dut.io_ntt_validin = 1;
    tick(dut);
    dut.io_ntt_validin = 0;

    int watchdog = 0;
    while (!dut.io_ntt_validout) {
        tick(dut);
        if (++watchdog > 200) {
            std::cerr << "small HOGE NTT validout timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;
    for (int lane = 0; lane < kN; ++lane) output[lane] = ntt_out(dut, lane);
    tick(dut);
    return true;
}
}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    auto table = cuHEpp::TableGen<kNbit>();
    auto twist = cuHEpp::TwistGen<kNbit>();
    std::mt19937 rng(0x483332U);
    int max_intt_wait_cycles = 0;
    int max_ntt_wait_cycles = 0;

    for (int test = 0; test < kTests; ++test) {
        std::array<uint32_t, kN> poly{};
        for (int i = 0; i < kN; ++i) {
            if (test == 0)
                poly[i] = static_cast<uint32_t>(i);
            else if (test == 1)
                poly[i] = (i & 1) ? 0xffffffffu : 0u;
            else
                poly[i] = rng();
        }

        std::array<cuHEpp::INTorus, kN> expected_intt{};
        cuHEpp::TwistINTT<uint32_t, kNbit>(expected_intt, poly, (*table)[1], (*twist)[1]);

        VSmallHoge32P64Rtl intt_dut;
        reset(intt_dut);
        std::array<uint64_t, kN> got_intt{};
        int intt_wait_cycles = 0;
        if (!run_intt(intt_dut, poly, got_intt, intt_wait_cycles)) return 1;
        intt_dut.final();
        max_intt_wait_cycles = std::max(max_intt_wait_cycles, intt_wait_cycles);
        for (int i = 0; i < kN; ++i) {
            if (got_intt[i] != expected_intt[i].value) {
                std::cerr << "small HOGE INTT mismatch index=" << i
                          << " got=" << got_intt[i]
                          << " want=" << expected_intt[i].value << "\n";
                return 1;
            }
        }

        std::array<cuHEpp::INTorus, kN> ntt_input = expected_intt;
        std::array<uint32_t, kN> expected_ntt{};
        cuHEpp::NTTradixButterfly<kNbit>(ntt_input.data(), kN);
        cuHEpp::TwistMulDirect<uint32_t, kNbit>(expected_ntt, ntt_input, (*twist)[0]);

        std::array<uint64_t, kN> ntt_words{};
        for (int i = 0; i < kN; ++i) ntt_words[i] = expected_intt[i].value;
        VSmallHoge32P64Rtl ntt_dut;
        reset(ntt_dut);
        std::array<uint32_t, kN> got_ntt{};
        int ntt_wait_cycles = 0;
        if (!run_ntt(ntt_dut, ntt_words, got_ntt, ntt_wait_cycles)) return 1;
        ntt_dut.final();
        max_ntt_wait_cycles = std::max(max_ntt_wait_cycles, ntt_wait_cycles);
        for (int i = 0; i < kN; ++i) {
            if (got_ntt[i] != expected_ntt[i]) {
                std::cerr << "small HOGE NTT mismatch index=" << i
                          << " got=" << got_ntt[i]
                          << " want=" << expected_ntt[i] << "\n";
                return 1;
            }
        }
    }

    std::cout << "METRIC small_hoge32_p64_tests=" << kTests << "\n";
    std::cout << "METRIC small_hoge32_p64_intt_input_cycles=1\n";
    std::cout << "METRIC small_hoge32_p64_intt_output_cycles=1\n";
    std::cout << "METRIC small_hoge32_p64_intt_max_wait_cycles="
              << max_intt_wait_cycles << "\n";
    std::cout << "METRIC small_hoge32_p64_ntt_input_cycles=1\n";
    std::cout << "METRIC small_hoge32_p64_ntt_output_cycles=1\n";
    std::cout << "METRIC small_hoge32_p64_ntt_max_wait_cycles="
              << max_ntt_wait_cycles << "\n";
    std::cout << "PASS small_hoge32_reference_test\n";
    return 0;
}
