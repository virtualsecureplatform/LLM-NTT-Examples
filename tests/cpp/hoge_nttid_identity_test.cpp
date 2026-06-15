#include <verilated.h>
#include <VNTTidPackedTop.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <random>

namespace {
constexpr int kN = 1024;
constexpr int kCycleBit = 3;
constexpr int kWaitCycles = (1 << (kCycleBit + 2)) + 1;
constexpr uint64_t kP = 0xffffffff00000001ULL;

void tick(VNTTidPackedTop &dut)
{
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.clock = 0;
    dut.eval();
}

void reset(VNTTidPackedTop &dut)
{
    dut.reset = 1;
    for (int i = 0; i < 2 * kN; ++i) dut.io_in[i] = 0;
    tick(dut);
    tick(dut);
    dut.reset = 0;
}
}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);

    std::mt19937_64 rng(0x4e545469ULL);
    for (int test = 0; test < 3; ++test) {
        VNTTidPackedTop dut;
        reset(dut);

        std::array<uint64_t, kN> input{};
        for (int i = 0; i < kN; ++i) {
            if (test == 0)
                input[i] = static_cast<uint64_t>(i);
            else if (test == 1)
                input[i] = (static_cast<uint64_t>(i) * 2654435761ULL) & ((1ULL << 63) - 1);
            else
                input[i] = rng() & ((1ULL << 63) - 1);
            dut.io_in[2 * i] = static_cast<uint32_t>(input[i]);
            dut.io_in[2 * i + 1] = static_cast<uint32_t>(input[i] >> 32);
        }

        for (int i = 0; i < kWaitCycles; ++i) tick(dut);

        for (int i = 0; i < kN; ++i) {
            const uint64_t got_raw =
                static_cast<uint64_t>(dut.io_out[2 * i]) |
                (static_cast<uint64_t>(dut.io_out[2 * i + 1]) << 32);
            const uint64_t got = got_raw % kP;
            const uint64_t want = input[i] % kP;
            if (got != want) {
                std::cerr << "NTTid mismatch index=" << i << " got=" << got
                          << " want=" << want << "\n";
                return 1;
            }
        }
        dut.final();
    }
    std::cout << "METRIC hoge_nttid_tests=3\n";
    std::cout << "METRIC hoge_nttid_wait_cycles=" << kWaitCycles << "\n";
    std::cout << "METRIC hoge_nttid_coefficients=" << kN << "\n";
    std::cout << "PASS hoge_nttid_identity_test\n";
    return 0;
}
