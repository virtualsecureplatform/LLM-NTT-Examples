#include <verilated.h>
#include <VINTTWrap.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <random>

#include "cuhe++.hpp"

namespace {
constexpr int kNbit = 10;
constexpr int kN = 1 << kNbit;
constexpr int kRadix = 32;
constexpr int kCycles = kN / kRadix;

void tick(VINTTWrap &dut)
{
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.clock = 0;
    dut.eval();
}

void reset(VINTTWrap &dut)
{
    dut.reset = 1;
    dut.io_enable = 0;
    for (int i = 0; i < kRadix; ++i) dut.io_in[i] = 0;
    tick(dut);
    tick(dut);
    dut.reset = 0;
}
}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);

    auto table = cuHEpp::TableGen<kNbit>();
    auto twist = cuHEpp::TwistGen<kNbit>();

    std::mt19937 rng(0x5354524dU);
    std::uniform_int_distribution<uint32_t> dist(0, UINT32_MAX);
    int max_wait_cycles = 0;

    for (int test = 0; test < 3; ++test) {
        VINTTWrap dut;
        reset(dut);

        std::array<uint32_t, kN> poly{};
        for (int i = 0; i < kN; ++i)
            poly[i] = (test == 0) ? static_cast<uint32_t>(i) : dist(rng);

        std::array<cuHEpp::INTorus, kN> expected{};
        cuHEpp::TwistINTT<uint32_t, kNbit>(expected, poly, (*table)[1], (*twist)[1]);

        dut.io_enable = 1;
        for (int cycle = 0; cycle < kCycles; ++cycle) {
            for (int lane = 0; lane < kRadix; ++lane)
                dut.io_in[lane] = poly[lane * kRadix + cycle];
            tick(dut);
        }

        int watchdog = 0;
        while (!dut.io_validout) {
            tick(dut);
            if (++watchdog > 4000) {
                std::cerr << "HOGE streaming INTT validout timeout\n";
                return 1;
            }
        }
        if (watchdog > max_wait_cycles) max_wait_cycles = watchdog;

        for (int cycle = 0; cycle < kCycles; ++cycle) {
            if (!dut.io_validout) {
                std::cerr << "HOGE streaming INTT validout dropped at cycle "
                          << cycle << "\n";
                return 1;
            }
            for (int lane = 0; lane < kRadix; ++lane) {
                const int index = cycle * kRadix + lane;
                const uint64_t got =
                    static_cast<uint64_t>(dut.io_out[2 * lane]) |
                    (static_cast<uint64_t>(dut.io_out[2 * lane + 1]) << 32);
                const uint64_t want = expected[index].value;
                if (got != want) {
                    std::cerr << "HOGE streaming INTT mismatch index=" << index
                              << " lane=" << lane << " cycle=" << cycle
                              << " got=" << got << " want=" << want << "\n";
                    return 1;
                }
            }
            tick(dut);
        }
        dut.io_enable = 0;
        tick(dut);
        dut.final();
    }
    std::cout << "METRIC hoge_streaming_intt_tests=3\n";
    std::cout << "METRIC hoge_streaming_intt_input_cycles=" << kCycles << "\n";
    std::cout << "METRIC hoge_streaming_intt_output_cycles=" << kCycles << "\n";
    std::cout << "METRIC hoge_streaming_intt_max_wait_cycles=" << max_wait_cycles
              << "\n";
    std::cout << "PASS hoge_streaming_reference_test\n";
    return 0;
}
