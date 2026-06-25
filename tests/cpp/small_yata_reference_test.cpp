#include <verilated.h>
#include SMALL_YATA_TOP_HEADER

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <random>

#include "raintt.hpp"

namespace {
using Dut = SMALL_YATA_TOP_TYPE;
constexpr int kNbit = SMALL_YATA_NBIT;
constexpr int kN = 1 << kNbit;
constexpr int kLanes = 8;
constexpr int kCycles = SMALL_YATA_CYCLES;
constexpr int kWordBits = 27;
constexpr int kTests = 3;
constexpr uint32_t kSignedMask = (1U << kWordBits) - 1;
constexpr const char *kMetricPrefix = SMALL_YATA_METRIC_PREFIX;
constexpr int64_t kP = 40960001;

void tick(Dut &dut)
{
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.clock = 0;
    dut.eval();
}

int32_t sign_extend(uint32_t value)
{
    const uint32_t sign = 1U << (kWordBits - 1);
    return static_cast<int32_t>((value ^ sign) - sign);
}

uint32_t pack_sint27(int32_t value) { return static_cast<uint32_t>(value) & kSignedMask; }

bool same_mod_p(int32_t got, int32_t want)
{
    int64_t diff = static_cast<int64_t>(got) - static_cast<int64_t>(want);
    diff %= kP;
    if (diff < 0) diff += kP;
    return diff == 0;
}

#define SMALL_YATA_FOR_EACH_LANE(X) X(0) X(1) X(2) X(3) X(4) X(5) X(6) X(7)

IData &intt_in(Dut &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_intt_in_##n;
        SMALL_YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData &ntt_in(Dut &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_ntt_in_##n;
        SMALL_YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData intt_out(const Dut &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_intt_out_##n;
        SMALL_YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData ntt_out(const Dut &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) case n: return dut.io_ntt_out_##n;
        SMALL_YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

void reset(Dut &dut)
{
    dut.reset = 1;
    dut.io_intt_validin = 0;
    dut.io_ntt_validin = 0;
    for (int lane = 0; lane < kLanes; ++lane) {
        intt_in(dut, lane) = 0;
        ntt_in(dut, lane) = 0;
    }
    tick(dut);
    tick(dut);
    dut.reset = 0;
}

template <typename Table, typename Twist>
void expected_yata_ntt(std::array<uint32_t, kN> &out,
                       std::array<raintt::DoubleSWord, kN> &in,
                       const Table &table, const Twist &twist)
{
    if constexpr (kNbit == 3) {
        (void)table;
        raintt::NTTradixButterfly<3>(in.data(), kN);
        raintt::TwistMulDirect<uint32_t, kNbit, true>(out, in, twist);
    } else {
        raintt::TwistNTT<uint32_t, kNbit, true>(out, in, table, twist);
    }
}

bool run_intt(Dut &dut, const std::array<uint32_t, kN> &input,
              std::array<int32_t, kN> &output, int &wait_cycles)
{
    for (int cycle = 0; cycle < kCycles; ++cycle) {
        for (int lane = 0; lane < kLanes; ++lane)
            intt_in(dut, lane) = input[lane * kCycles + cycle];
        dut.io_intt_validin = 1;
        tick(dut);
    }
    dut.io_intt_validin = 0;

    int watchdog = 0;
    while (!dut.io_intt_validout) {
        tick(dut);
        if (++watchdog > 500) {
            std::cerr << "small YATA INTT validout timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;
    for (int cycle = 0; cycle < kCycles; ++cycle) {
        if (!dut.io_intt_validout) {
            std::cerr << "small YATA INTT validout dropped at cycle "
                      << cycle << "\n";
            return false;
        }
        for (int lane = 0; lane < kLanes; ++lane)
            output[cycle * kLanes + lane] = sign_extend(intt_out(dut, lane));
        tick(dut);
    }
    return true;
}

bool run_ntt(Dut &dut, const std::array<int32_t, kN> &input,
             std::array<uint32_t, kN> &output, int &wait_cycles)
{
    for (int cycle = 0; cycle < kCycles; ++cycle) {
        for (int lane = 0; lane < kLanes; ++lane)
            ntt_in(dut, lane) = pack_sint27(input[cycle * kLanes + lane]);
        dut.io_ntt_validin = 1;
        tick(dut);
    }
    dut.io_ntt_validin = 0;

    int watchdog = 0;
    while (!dut.io_ntt_validout) {
        tick(dut);
        if (++watchdog > 500) {
            std::cerr << "small YATA NTT validout timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;
    for (int cycle = 0; cycle < kCycles; ++cycle) {
        if (!dut.io_ntt_validout) {
            std::cerr << "small YATA NTT validout dropped at cycle "
                      << cycle << "\n";
            return false;
        }
        for (int lane = 0; lane < kLanes; ++lane)
            output[lane * kCycles + cycle] = ntt_out(dut, lane);
        tick(dut);
    }
    return true;
}
}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    auto table = raintt::TableGen<kNbit>();
    auto twist = raintt::TwistGen<kNbit, 3>();
    std::mt19937 rng(0x59415441U + kNbit);
    std::uniform_int_distribution<uint32_t> dist(0, static_cast<uint32_t>(raintt::P) - 1);
    int max_intt_wait_cycles = 0;
    int max_ntt_wait_cycles = 0;

    for (int test = 0; test < kTests; ++test) {
        std::array<uint32_t, kN> poly{};
        for (int i = 0; i < kN; ++i) {
            if (test == 0)
                poly[i] = static_cast<uint32_t>(i) % static_cast<uint32_t>(raintt::P);
            else if (test == 1)
                poly[i] = (i & 1) ? static_cast<uint32_t>(raintt::P) - 1 : 0;
            else
                poly[i] = dist(rng);
        }

        std::array<raintt::DoubleSWord, kN> expected_intt{};
        raintt::TwistINTT<uint32_t, kNbit, false>(
            expected_intt, poly, (*table)[1], (*twist)[1]);

        Dut intt_dut;
        reset(intt_dut);
        std::array<int32_t, kN> got_intt{};
        int intt_wait_cycles = 0;
        if (!run_intt(intt_dut, poly, got_intt, intt_wait_cycles)) return 1;
        intt_dut.final();
        max_intt_wait_cycles = std::max(max_intt_wait_cycles, intt_wait_cycles);
        for (int i = 0; i < kN; ++i) {
            const int32_t want = static_cast<int32_t>(expected_intt[i]);
            if (!same_mod_p(got_intt[i], want)) {
                std::cerr << "small YATA INTT mismatch test=" << test
                          << " index=" << i
                          << " got=" << got_intt[i] << " want=" << want << "\n";
                std::cerr << "got:";
                for (int j = 0; j < kN; ++j) std::cerr << " " << got_intt[j];
                std::cerr << "\nwant:";
                for (int j = 0; j < kN; ++j)
                    std::cerr << " " << static_cast<int32_t>(expected_intt[j]);
                std::cerr << "\n";
                return 1;
            }
        }

        std::array<raintt::DoubleSWord, kN> ntt_input = expected_intt;
        std::array<uint32_t, kN> expected_ntt{};
        expected_yata_ntt(expected_ntt, ntt_input, (*table)[0], (*twist)[0]);

        std::array<int32_t, kN> ntt_words{};
        for (int i = 0; i < kN; ++i)
            ntt_words[i] = static_cast<int32_t>(expected_intt[i]);
        Dut ntt_dut;
        reset(ntt_dut);
        std::array<uint32_t, kN> got_ntt{};
        int ntt_wait_cycles = 0;
        if (!run_ntt(ntt_dut, ntt_words, got_ntt, ntt_wait_cycles)) return 1;
        ntt_dut.final();
        max_ntt_wait_cycles = std::max(max_ntt_wait_cycles, ntt_wait_cycles);
        for (int i = 0; i < kN; ++i) {
            if (got_ntt[i] != expected_ntt[i]) {
                std::cerr << "small YATA NTT mismatch index=" << i
                          << " got=" << got_ntt[i]
                          << " want=" << expected_ntt[i] << "\n";
                return 1;
            }
        }
    }

    std::cout << "METRIC " << kMetricPrefix << "_tests=" << kTests << "\n";
    std::cout << "METRIC " << kMetricPrefix << "_intt_input_cycles=" << kCycles << "\n";
    std::cout << "METRIC " << kMetricPrefix << "_intt_output_cycles=" << kCycles << "\n";
    std::cout << "METRIC " << kMetricPrefix << "_intt_max_wait_cycles="
              << max_intt_wait_cycles << "\n";
    std::cout << "METRIC " << kMetricPrefix << "_ntt_input_cycles=" << kCycles << "\n";
    std::cout << "METRIC " << kMetricPrefix << "_ntt_output_cycles=" << kCycles << "\n";
    std::cout << "METRIC " << kMetricPrefix << "_ntt_max_wait_cycles="
              << max_ntt_wait_cycles << "\n";
    std::cout << "PASS small_yata_reference_test\n";
    return 0;
}
