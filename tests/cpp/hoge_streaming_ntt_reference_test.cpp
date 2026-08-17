#include <verilated.h>
#include <VNTTWrap.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <random>

#include "cuhe++.hpp"

namespace {
constexpr int kNbit = 10;
constexpr int kN = 1 << kNbit;
constexpr int kLanes = 32;
constexpr int kCycles = kN / kLanes;

void tick(VNTTWrap &dut)
{
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.clock = 0;
    dut.eval();
}

void reset(VNTTWrap &dut)
{
    dut.reset = 1;
    dut.io_enable = 0;
    for (int i = 0; i < 2 * kLanes; ++i) dut.io_in[i] = 0;
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
    std::mt19937_64 rng(0x4e47454e48544745ULL);
    int max_wait_cycles = 0;

    for (int test = 0; test < 3; ++test) {
        std::array<cuHEpp::INTorus, kN> input{};
        for (int i = 0; i < kN; ++i)
            input[i] = cuHEpp::INTorus(test == 0 ? static_cast<uint64_t>(i) : rng());

        auto expected = input;
        cuHEpp::NTT<kNbit, 5>(expected, (*table)[0]);
        const auto inverse_size = cuHEpp::InvPow2(kNbit);
        for (int i = 0; i < kN; ++i)
            expected[i] *= (*twist)[0][i] * inverse_size;

        VNTTWrap dut;
        reset(dut);
        dut.io_enable = 1;
        for (int cycle = 0; cycle < kCycles; ++cycle) {
            for (int lane = 0; lane < kLanes; ++lane) {
                const uint64_t value = input[cycle * kLanes + lane].value;
                dut.io_in[2 * lane] = static_cast<uint32_t>(value);
                dut.io_in[2 * lane + 1] = static_cast<uint32_t>(value >> 32);
            }
            tick(dut);
            if (cycle + 1 < kCycles && !dut.io_ready) {
                std::cerr << "HOGE NTT ready dropped during input\n";
                return 1;
            }
        }

        int watchdog = 0;
        while (!dut.io_validout) {
            tick(dut);
            if (++watchdog > 4000) {
                std::cerr << "HOGE streaming NTT validout timeout\n";
                return 1;
            }
        }
        max_wait_cycles = std::max(max_wait_cycles, watchdog);
        for (int cycle = 0; cycle < kCycles; ++cycle) {
            if (!dut.io_validout) {
                std::cerr << "HOGE streaming NTT validout dropped\n";
                return 1;
            }
            for (int lane = 0; lane < kLanes; ++lane) {
                const uint64_t got = static_cast<uint64_t>(dut.io_out[2 * lane]) |
                                     (static_cast<uint64_t>(dut.io_out[2 * lane + 1]) << 32);
                const uint64_t want = expected[cycle * kLanes + lane].value;
                if (got != want) {
                    std::cerr << "HOGE NTT mismatch test=" << test
                              << " index=" << cycle * kLanes + lane
                              << " got=" << got << " want=" << want << '\n';
                    return 1;
                }
            }
            tick(dut);
        }
        dut.io_enable = 0;
        tick(dut);
        dut.final();
    }
    std::cout << "METRIC hoge_streaming_ntt_tests=3\n";
    std::cout << "METRIC hoge_streaming_ntt_input_cycles=" << kCycles << '\n';
    std::cout << "METRIC hoge_streaming_ntt_output_cycles=" << kCycles << '\n';
    std::cout << "METRIC hoge_streaming_ntt_max_wait_cycles=" << max_wait_cycles << '\n';
    std::cout << "PASS hoge_streaming_ntt_reference_test\n";
    return 0;
}
