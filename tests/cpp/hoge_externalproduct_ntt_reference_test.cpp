#include <verilated.h>
#include <VExternalProductWrap.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <random>
#include <tuple>

#include "cuhe++.hpp"
#include "params.hpp"
#include "tfhe/trgsw.hpp"

namespace {
using P = TFHEpp::lvl1param;
using TrgswNtt = TFHEpp::TRGSWNTT<P>;

constexpr int kN = P::n;
constexpr int kRadix = 32;
constexpr int kNumCycle = 32;
constexpr int kFiber = kN / kNumCycle;
constexpr int kRows = std::tuple_size<TrgswNtt>::value;
constexpr int kComponents = P::k + 1;
constexpr int kIdleBetweenComponents = kRadix;
constexpr int kWatchdogCycles = 5000;

static_assert(kN == 1024);
static_assert(kFiber == 32);
static_assert(kComponents == 2);

struct TrgswStream {
    const TrgswNtt &value;
    int cycle = 0;

    bool valid() const { return (cycle / kNumCycle) < kRows; }
};

void pack_trgsw(VExternalProductWrap &dut, const TrgswStream &stream)
{
    dut.io_trgswinvalid = stream.valid();
    if (!stream.valid() || !dut.io_trgswinready) return;

    const int row = stream.cycle / kNumCycle;
    const int cycle = stream.cycle % kNumCycle;
    for (int component = 0; component < kComponents; ++component) {
        for (int lane = 0; lane < kFiber; ++lane) {
            const uint64_t word =
                stream.value[row][component][cycle * kFiber + lane].value;
            const int out_index = 2 * (component * kFiber + lane);
            dut.io_trgswin[out_index] = static_cast<uint32_t>(word);
            dut.io_trgswin[out_index + 1] = static_cast<uint32_t>(word >> 32);
        }
    }
}

void tick(VExternalProductWrap &dut, TrgswStream &stream)
{
    dut.eval();
    dut.clock = !dut.clock;
    pack_trgsw(dut, stream);

    dut.eval();
    dut.clock = !dut.clock;
    pack_trgsw(dut, stream);
    if (stream.valid() && dut.io_trgswinready) ++stream.cycle;
}

void reset(VExternalProductWrap &dut)
{
    dut.reset = 1;
    dut.clock = 1;
    dut.io_validin = 0;
    dut.io_trgswinvalid = 0;
    for (int i = 0; i < 32; ++i) {
        dut.io_in[i] = 0;
        dut.io_out[i] = 0;
    }
    for (int i = 0; i < 128; ++i) dut.io_trgswin[i] = 0;

    dut.eval();
    dut.clock = 0;
    dut.eval();
    dut.clock = 1;
    dut.eval();
    dut.reset = 0;
}

void drive_component(VExternalProductWrap &dut, TrgswStream &stream,
                     const TFHEpp::Polynomial<P> &poly)
{
    dut.io_validin = 1;
    for (int cycle = 0; cycle < kRadix; ++cycle) {
        for (int lane = 0; lane < kRadix; ++lane)
            dut.io_in[lane] = poly[lane * kFiber + cycle];
        tick(dut, stream);
    }
    dut.io_validin = 0;
}

void idle(VExternalProductWrap &dut, TrgswStream &stream, int cycles)
{
    dut.io_validin = 0;
    for (int i = 0; i < cycles; ++i) tick(dut, stream);
}

void fill_trgsw(TrgswNtt &trgswntt)
{
    std::mt19937_64 rng(0x484f47454e545455ULL);
    std::uniform_int_distribution<uint64_t> dist(0, cuHEpp::P - 1);
    for (auto &row : trgswntt)
        for (auto &component : row)
            for (auto &coefficient : component)
                coefficient = cuHEpp::INTorus(dist(rng), false);
}

void fill_input(TFHEpp::TRLWE<P> &input, int test)
{
    std::mt19937 rng(0x45585450U + static_cast<uint32_t>(test));
    std::uniform_int_distribution<uint32_t> dist(
        0, std::numeric_limits<uint32_t>::max());

    for (int component = 0; component < kComponents; ++component) {
        for (int index = 0; index < kN; ++index) {
            if (test == 0) {
                input[component][index] =
                    static_cast<uint32_t>(component * kN + index);
            }
            else {
                input[component][index] = dist(rng);
            }
        }
    }
}

bool capture_output(VExternalProductWrap &dut, TrgswStream &stream,
                    TFHEpp::TRLWE<P> &observed, int &wait_cycles)
{
    wait_cycles = 0;
    while (!dut.io_validout) {
        tick(dut, stream);
        if (++wait_cycles > kWatchdogCycles) {
            std::cerr << "HOGE ExternalProduct validout timeout\n";
            return false;
        }
    }

    for (int component = 0; component < kComponents; ++component) {
        for (int cycle = 0; cycle < kRadix; ++cycle) {
            int gap_cycles = 0;
            while (!dut.io_validout) {
                tick(dut, stream);
                if (++gap_cycles > kWatchdogCycles) {
                    std::cerr << "HOGE ExternalProduct validout gap timeout\n";
                    return false;
                }
            }
            for (int lane = 0; lane < kRadix; ++lane)
                observed[component][lane * kRadix + cycle] = dut.io_out[lane];
            tick(dut, stream);
        }
    }
    return true;
}
}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);

    auto trgswntt = std::make_unique<TrgswNtt>();
    fill_trgsw(*trgswntt);

    int max_wait_cycles = 0;
    constexpr int kTests = 2;
    VExternalProductWrap dut;
    reset(dut);
    for (int test = 0; test < kTests; ++test) {
        TFHEpp::TRLWE<P> input{};
        fill_input(input, test);

        TFHEpp::TRLWE<P> expected{};
        TFHEpp::ExternalProduct<P>(expected, input, *trgswntt);

        TrgswStream stream{*trgswntt};
        drive_component(dut, stream, input[0]);
        idle(dut, stream, kIdleBetweenComponents);
        drive_component(dut, stream, input[1]);
        dut.io_validin = 0;

        TFHEpp::TRLWE<P> observed{};
        int wait_cycles = 0;
        if (!capture_output(dut, stream, observed, wait_cycles)) return 1;
        if (wait_cycles > max_wait_cycles) max_wait_cycles = wait_cycles;

        for (int component = 0; component < kComponents; ++component) {
            for (int index = 0; index < kN; ++index) {
                if (observed[component][index] != expected[component][index]) {
                    std::cerr << "HOGE ExternalProduct NTT mismatch test="
                              << test << " component=" << component
                              << " index=" << index
                              << " got=" << observed[component][index]
                              << " want=" << expected[component][index]
                              << "\n";
                    return 1;
                }
            }
        }
    }
    dut.final();

    std::cout << "METRIC hoge_externalproduct_ntt_tests=" << kTests << "\n";
    std::cout << "METRIC hoge_externalproduct_ntt_trgsw_rows=" << kRows
              << "\n";
    std::cout << "METRIC hoge_externalproduct_ntt_input_cycles="
              << (kComponents * kRadix + kIdleBetweenComponents) << "\n";
    std::cout << "METRIC hoge_externalproduct_ntt_output_cycles="
              << (kComponents * kRadix) << "\n";
    std::cout << "METRIC hoge_externalproduct_ntt_max_wait_cycles="
              << max_wait_cycles << "\n";
    std::cout << "PASS hoge_externalproduct_ntt_reference_test\n";
    return 0;
}
