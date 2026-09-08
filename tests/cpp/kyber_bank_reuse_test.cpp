#define KYBER_PE1_DATA_DIR "vectors"
#define main original_reference_main
#include "kyber_pe1_reference_test.cpp"
#undef main

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    const Poly a = read_poly("KYBER_DIN0.txt");
    const Poly b = read_poly("KYBER_DIN1.txt");
    const Poly fa = read_poly("KYBER_DIN0_MFNTT.txt");
    const Poly fb = read_poly("KYBER_DIN1_MFNTT.txt");
    VKyberHPM1PE dut;
    reset(dut);
    load_fntt(dut, a, false);
    load_fntt(dut, b, true);
    int wait_cycles = 0;
    for (int epoch = 0; epoch < 4; ++epoch) {
        if (!start_and_wait(dut, false, false, wait_cycles)) return 1;
        if (!compare_poly("A forward", read_fntt(dut, false), fa)) return 1;
        if (!compare_poly("B preserved during A forward", read_fntt(dut, true), b)) return 1;
        if (!start_and_wait(dut, true, false, wait_cycles)) return 1;
        if (!compare_poly("A preserved during B forward", read_fntt(dut, false), fa)) return 1;
        if (!compare_poly("B forward", read_fntt(dut, true), fb)) return 1;
        if (!start_and_wait(dut, false, true, wait_cycles)) return 1;
        if (!compare_poly("A inverse", read_intt(dut, false), a)) return 1;
        if (!compare_poly("B preserved during A inverse", read_intt(dut, true), fb)) return 1;
        if (!start_and_wait(dut, true, true, wait_cycles)) return 1;
        if (!compare_poly("B inverse", read_intt(dut, true), b)) return 1;
        if (!compare_poly("A preserved during B inverse", read_intt(dut, false), a)) return 1;
    }
    dut.final();
    std::cout << "PASS 16 Kyber operations without reset or reload; other bank preserved\n";
    return 0;
}
