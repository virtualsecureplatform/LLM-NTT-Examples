#include <verilated.h>
#include <VKyberHPM1PE.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace {
constexpr int kN = 256;
constexpr int kWatchdogCycles = 2000;
constexpr const char *kDataDir = KYBER_PE1_DATA_DIR;
using Poly = std::array<uint16_t, kN>;

void tick(VKyberHPM1PE &dut)
{
    dut.clk = 0;
    dut.eval();
    dut.clk = 1;
    dut.eval();
    dut.clk = 0;
    dut.eval();
}

void clear_controls(VKyberHPM1PE &dut)
{
    dut.load_a_f = 0;
    dut.load_a_i = 0;
    dut.load_b_f = 0;
    dut.load_b_i = 0;
    dut.read_a = 0;
    dut.read_b = 0;
    dut.start_ab = 0;
    dut.start_fntt = 0;
    dut.start_pwm2 = 0;
    dut.start_intt = 0;
    dut.din = 0;
}

void reset(VKyberHPM1PE &dut)
{
    dut.reset = 0;
    clear_controls(dut);
    tick(dut);
    dut.reset = 1;
    tick(dut);
    tick(dut);
    dut.reset = 0;
    tick(dut);
}

Poly read_poly(const std::string &name)
{
    std::ifstream input(std::string(kDataDir) + "/" + name);
    if (!input) {
        std::cerr << "failed to open Kyber vector " << name << "\n";
        std::exit(1);
    }

    Poly poly{};
    std::string line;
    int index = 0;
    while (std::getline(input, line)) {
        const auto comment = line.find_first_of("#/");
        if (comment != std::string::npos) line.erase(comment);
        std::istringstream fields(line);
        std::string token;
        while (fields >> token) {
            if (index >= kN) {
                std::cerr << "too many coefficients in " << name << "\n";
                std::exit(1);
            }
            poly[index++] = static_cast<uint16_t>(std::stoul(token, nullptr, 16) & 0xfff);
        }
    }
    if (index != kN) {
        std::cerr << "expected " << kN << " coefficients in " << name
                  << ", got " << index << "\n";
        std::exit(1);
    }
    return poly;
}

bool compare_poly(const char *label, const Poly &got, const Poly &want)
{
    for (int i = 0; i < kN; ++i) {
        if ((got[i] & 0xfff) != (want[i] & 0xfff)) {
            std::cerr << label << " mismatch index=" << i
                      << " got=0x" << std::hex << (got[i] & 0xfff)
                      << " want=0x" << (want[i] & 0xfff) << std::dec << "\n";
            return false;
        }
    }
    return true;
}

void load_fntt(VKyberHPM1PE &dut, const Poly &input, bool load_b)
{
    clear_controls(dut);
    if (load_b)
        dut.load_b_f = 1;
    else
        dut.load_a_f = 1;
    tick(dut);
    clear_controls(dut);

    for (uint16_t coeff : input) {
        dut.din = coeff & 0xfff;
        tick(dut);
    }
    clear_controls(dut);
    tick(dut);
    tick(dut);
}

void load_intt(VKyberHPM1PE &dut, const Poly &input, bool load_b)
{
    clear_controls(dut);
    if (load_b)
        dut.load_b_i = 1;
    else
        dut.load_a_i = 1;
    tick(dut);
    clear_controls(dut);

    for (int k = 0; k < 64; ++k) {
        dut.din = input[4 * k + 0] & 0xfff;
        tick(dut);
        dut.din = input[4 * k + 2] & 0xfff;
        tick(dut);
        dut.din = input[4 * k + 1] & 0xfff;
        tick(dut);
        dut.din = input[4 * k + 3] & 0xfff;
        tick(dut);
    }
    clear_controls(dut);
    tick(dut);
    tick(dut);
}

bool start_and_wait(VKyberHPM1PE &dut, bool operand_b, bool inverse, int &wait_cycles)
{
    clear_controls(dut);
    dut.start_ab = operand_b ? 1 : 0;
    if (inverse)
        dut.start_intt = 1;
    else
        dut.start_fntt = 1;
    tick(dut);
    clear_controls(dut);
    tick(dut);
    tick(dut);

    int watchdog = 0;
    while (!dut.done) {
        tick(dut);
        if (++watchdog > kWatchdogCycles) {
            std::cerr << (inverse ? "Kyber INTT" : "Kyber FNTT")
                      << " done timeout\n";
            return false;
        }
    }
    wait_cycles = watchdog;
    tick(dut);
    return true;
}

Poly read_fntt(VKyberHPM1PE &dut, bool read_b)
{
    clear_controls(dut);
    if (read_b)
        dut.read_b = 1;
    else
        dut.read_a = 1;
    tick(dut);
    clear_controls(dut);
    tick(dut);
    tick(dut);

    Poly output{};
    for (int m = 0; m < 64; ++m) {
        output[4 * m + 0] = dut.dout & 0xfff;
        tick(dut);
        output[4 * m + 2] = dut.dout & 0xfff;
        tick(dut);
        output[4 * m + 1] = dut.dout & 0xfff;
        tick(dut);
        output[4 * m + 3] = dut.dout & 0xfff;
        tick(dut);
    }
    return output;
}

Poly read_intt(VKyberHPM1PE &dut, bool read_b)
{
    clear_controls(dut);
    if (read_b)
        dut.read_b = 1;
    else
        dut.read_a = 1;
    tick(dut);
    clear_controls(dut);
    tick(dut);
    tick(dut);

    Poly output{};
    for (int m = 0; m < 128; ++m) {
        output[m] = dut.dout & 0xfff;
        tick(dut);
        output[m + 128] = dut.dout & 0xfff;
        tick(dut);
    }
    return output;
}

bool run_fntt_case(const char *label, const Poly &input, const Poly &expected,
                   bool operand_b, int &wait_cycles)
{
    VKyberHPM1PE dut;
    reset(dut);
    load_fntt(dut, input, operand_b);
    if (!start_and_wait(dut, operand_b, false, wait_cycles)) return false;
    const Poly got = read_fntt(dut, operand_b);
    dut.final();
    return compare_poly(label, got, expected);
}

bool run_intt_case(const char *label, const Poly &input, const Poly &expected,
                   bool operand_b, int &wait_cycles)
{
    VKyberHPM1PE dut;
    reset(dut);
    load_intt(dut, input, operand_b);
    if (!start_and_wait(dut, operand_b, true, wait_cycles)) return false;
    const Poly got = read_intt(dut, operand_b);
    dut.final();
    return compare_poly(label, got, expected);
}
}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);

    const Poly din0 = read_poly("KYBER_DIN0.txt");
    const Poly din1 = read_poly("KYBER_DIN1.txt");
    const Poly din0_mfntt = read_poly("KYBER_DIN0_MFNTT.txt");
    const Poly din1_mfntt = read_poly("KYBER_DIN1_MFNTT.txt");

    int max_fntt_wait_cycles = 0;
    int max_intt_wait_cycles = 0;
    int wait_cycles = 0;

    if (!run_fntt_case("Kyber FNTT A", din0, din0_mfntt, false, wait_cycles)) return 1;
    max_fntt_wait_cycles = std::max(max_fntt_wait_cycles, wait_cycles);
    if (!run_fntt_case("Kyber FNTT B", din1, din1_mfntt, true, wait_cycles)) return 1;
    max_fntt_wait_cycles = std::max(max_fntt_wait_cycles, wait_cycles);
    if (!run_intt_case("Kyber INTT A", din0_mfntt, din0, false, wait_cycles)) return 1;
    max_intt_wait_cycles = std::max(max_intt_wait_cycles, wait_cycles);
    if (!run_intt_case("Kyber INTT B", din1_mfntt, din1, true, wait_cycles)) return 1;
    max_intt_wait_cycles = std::max(max_intt_wait_cycles, wait_cycles);

    std::cout << "METRIC kyber_pe1_fntt_tests=2\n";
    std::cout << "METRIC kyber_pe1_fntt_input_cycles=256\n";
    std::cout << "METRIC kyber_pe1_fntt_output_cycles=256\n";
    std::cout << "METRIC kyber_pe1_fntt_max_wait_cycles="
              << max_fntt_wait_cycles << "\n";
    std::cout << "METRIC kyber_pe1_intt_tests=2\n";
    std::cout << "METRIC kyber_pe1_intt_input_cycles=256\n";
    std::cout << "METRIC kyber_pe1_intt_output_cycles=256\n";
    std::cout << "METRIC kyber_pe1_intt_max_wait_cycles="
              << max_intt_wait_cycles << "\n";
    std::cout << "PASS kyber_pe1_reference_test\n";
    return 0;
}
