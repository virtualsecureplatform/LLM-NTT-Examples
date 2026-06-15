#include <verilated.h>
#include <VYataRainttTop.h>

#include <algorithm>
#include <array>
#include <cassert>
#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <random>

#include "raintt.hpp"

namespace {
constexpr int kNbit = 9;
constexpr int kN = 1 << kNbit;
constexpr int kLanes = 64;
constexpr int kCycles = kN / kLanes;
constexpr int kWordBits = 27;
constexpr uint32_t kSignedMask = (1U << kWordBits) - 1;

static_assert(kCycles == 8);

void tick(VYataRainttTop &dut)
{
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.clock = 0;
    dut.eval();
}

int32_t sign_extend(uint32_t value, int bits)
{
    const uint32_t sign = 1U << (bits - 1);
    return static_cast<int32_t>((value ^ sign) - sign);
}

uint32_t pack_sint27(int32_t value) { return static_cast<uint32_t>(value) & kSignedMask; }

#define YATA_FOR_EACH_LANE(X) \
    X(0)                      \
    X(1)                      \
    X(2)                      \
    X(3)                      \
    X(4)                      \
    X(5)                      \
    X(6)                      \
    X(7)                      \
    X(8)                      \
    X(9)                      \
    X(10)                     \
    X(11)                     \
    X(12)                     \
    X(13)                     \
    X(14)                     \
    X(15)                     \
    X(16)                     \
    X(17)                     \
    X(18)                     \
    X(19)                     \
    X(20)                     \
    X(21)                     \
    X(22)                     \
    X(23)                     \
    X(24)                     \
    X(25)                     \
    X(26)                     \
    X(27)                     \
    X(28)                     \
    X(29)                     \
    X(30)                     \
    X(31)                     \
    X(32)                     \
    X(33)                     \
    X(34)                     \
    X(35)                     \
    X(36)                     \
    X(37)                     \
    X(38)                     \
    X(39)                     \
    X(40)                     \
    X(41)                     \
    X(42)                     \
    X(43)                     \
    X(44)                     \
    X(45)                     \
    X(46)                     \
    X(47)                     \
    X(48)                     \
    X(49)                     \
    X(50)                     \
    X(51)                     \
    X(52)                     \
    X(53)                     \
    X(54)                     \
    X(55)                     \
    X(56)                     \
    X(57)                     \
    X(58)                     \
    X(59)                     \
    X(60)                     \
    X(61)                     \
    X(62)                     \
    X(63)

IData &intt_in(VYataRainttTop &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) \
    case n: return dut.io_intt_in_##n;
        YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData &ntt_in(VYataRainttTop &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) \
    case n: return dut.io_ntt_in_##n;
        YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData intt_out(const VYataRainttTop &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) \
    case n: return dut.io_intt_out_##n;
        YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

IData ntt_out(const VYataRainttTop &dut, int lane)
{
    switch (lane) {
#define CASE_PORT(n) \
    case n: return dut.io_ntt_out_##n;
        YATA_FOR_EACH_LANE(CASE_PORT)
#undef CASE_PORT
    default: std::abort();
    }
}

void reset(VYataRainttTop &dut)
{
    dut.reset = 1;
    dut.io_intt_validin = 0;
    dut.io_ntt_validin = 0;
    for (int i = 0; i < kLanes; ++i) {
        intt_in(dut, i) = 0;
        ntt_in(dut, i) = 0;
    }
    tick(dut);
    tick(dut);
    dut.reset = 0;
}

bool run_intt(VYataRainttTop &dut, const std::array<uint32_t, kN> &input,
              std::array<int32_t, kN> &output, int &wait_cycles)
{
    for (int cycle = 0; cycle < kCycles; ++cycle) {
        // INTT RTL indexes twist/input lanes as lane * numcycle + cycle.
        for (int lane = 0; lane < kLanes; ++lane)
            intt_in(dut, lane) = input[lane * kCycles + cycle];
        dut.io_intt_validin = 1;
        tick(dut);
    }
    dut.io_intt_validin = 0;

    int watchdog = 0;
    while (!dut.io_intt_validout) {
        tick(dut);
        if (++watchdog > 2000) {
            std::cerr << "INTT validout timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;

    for (int cycle = 0; cycle < kCycles; ++cycle) {
        if (!dut.io_intt_validout) {
            std::cerr << "INTT validout dropped at cycle " << cycle << "\n";
            return false;
        }
        for (int lane = 0; lane < kLanes; ++lane) {
            const int index = cycle * kLanes + lane;
            const int32_t got = sign_extend(intt_out(dut, lane), kWordBits);
            output[index] = got;
        }
        tick(dut);
    }
    return true;
}

bool run_ntt(VYataRainttTop &dut, const std::array<int32_t, kN> &input,
             const std::array<uint32_t, kN> &expected, int &wait_cycles)
{
    for (int cycle = 0; cycle < kCycles; ++cycle) {
        for (int lane = 0; lane < kLanes; ++lane) {
            const int index = cycle * kLanes + lane;
            ntt_in(dut, lane) = pack_sint27(input[index]);
        }
        dut.io_ntt_validin = 1;
        tick(dut);
    }
    dut.io_ntt_validin = 0;

    int watchdog = 0;
    while (!dut.io_ntt_validout) {
        tick(dut);
        if (++watchdog > 2000) {
            std::cerr << "NTT validout timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;

    for (int cycle = 0; cycle < kCycles; ++cycle) {
        if (!dut.io_ntt_validout) {
            std::cerr << "NTT validout dropped at cycle " << cycle << "\n";
            return false;
        }
        for (int lane = 0; lane < kLanes; ++lane) {
            const int index = lane * kCycles + cycle;
            const uint32_t got = ntt_out(dut, lane);
            const uint32_t want = expected[index];
            if (got != want) {
                std::cerr << "NTT mismatch index=" << index << " lane=" << lane
                          << " cycle=" << cycle << " got=" << got
                          << " want=" << want << "\n";
                return false;
            }
        }
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

    std::mt19937 rng(0x4c4c4dU);
    std::uniform_int_distribution<uint32_t> dist(0, static_cast<uint32_t>(raintt::P) - 1);
    int max_intt_wait_cycles = 0;
    int max_ntt_wait_cycles = 0;

    for (int test = 0; test < 4; ++test) {
        std::array<uint32_t, kN> poly{};
        for (int i = 0; i < kN; ++i) {
            if (test == 0)
                poly[i] = i % static_cast<uint32_t>(raintt::P);
            else if (test == 1)
                poly[i] = (i & 1) ? static_cast<uint32_t>(raintt::P) - 1 : 0;
            else
                poly[i] = dist(rng);
        }

        std::array<raintt::DoubleSWord, kN> fd{};
        raintt::TwistINTT<uint32_t, kNbit, false>(fd, poly, (*table)[1], (*twist)[1]);
        std::array<int32_t, kN> hardware_fd{};
        VYataRainttTop intt_dut;
        reset(intt_dut);
        int intt_wait_cycles = 0;
        if (!run_intt(intt_dut, poly, hardware_fd, intt_wait_cycles)) return 1;
        intt_dut.final();
        max_intt_wait_cycles = std::max(max_intt_wait_cycles, intt_wait_cycles);
        for (int i = 0; i < kN; ++i) {
            const int32_t want = static_cast<int32_t>(fd[i]);
            if (hardware_fd[i] != want) {
                std::cerr << "INTT mismatch index=" << i << " got=" << hardware_fd[i]
                          << " want=" << want << "\n";
                return 1;
            }
        }

        std::array<raintt::DoubleSWord, kN> ntt_input = fd;
        std::array<uint32_t, kN> ntt_expected{};
        raintt::TwistNTT<uint32_t, kNbit, true>(ntt_expected, ntt_input, (*table)[0],
                                                (*twist)[0]);
        std::array<int32_t, kN> reference_fd{};
        for (int i = 0; i < kN; ++i) reference_fd[i] = static_cast<int32_t>(fd[i]);
        VYataRainttTop ntt_dut;
        reset(ntt_dut);
        int ntt_wait_cycles = 0;
        if (!run_ntt(ntt_dut, reference_fd, ntt_expected, ntt_wait_cycles)) return 1;
        ntt_dut.final();
        max_ntt_wait_cycles = std::max(max_ntt_wait_cycles, ntt_wait_cycles);
    }
    std::cout << "METRIC yata_raintt_tests=4\n";
    std::cout << "METRIC yata_raintt_intt_input_cycles=" << kCycles << "\n";
    std::cout << "METRIC yata_raintt_intt_output_cycles=" << kCycles << "\n";
    std::cout << "METRIC yata_raintt_intt_max_wait_cycles=" << max_intt_wait_cycles
              << "\n";
    std::cout << "METRIC yata_raintt_ntt_input_cycles=" << kCycles << "\n";
    std::cout << "METRIC yata_raintt_ntt_output_cycles=" << kCycles << "\n";
    std::cout << "METRIC yata_raintt_ntt_max_wait_cycles=" << max_ntt_wait_cycles << "\n";
    std::cout << "PASS yata_raintt_reference_test\n";
    return 0;
}
