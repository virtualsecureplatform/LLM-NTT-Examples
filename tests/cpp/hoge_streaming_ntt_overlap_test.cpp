#include <verilated.h>
#include <VNTTWrap.h>
#include <array>
#include <cstdint>
#include <iostream>
#include <random>
#include <vector>
#include "cuhe++.hpp"

namespace {
using Frame = std::array<cuHEpp::INTorus, 1024>;
void tick(VNTTWrap &dut) {
    dut.clock=0; dut.eval(); dut.clock=1; dut.eval(); dut.clock=0; dut.eval();
}
void reset(VNTTWrap &dut) {
    dut.reset=1; dut.io_enable=0; tick(dut); tick(dut); dut.reset=0;
}
}

// Additional contract test for the full-throughput backend: fixed 32-cycle
// input frames, no output backpressure, and overlapping independent frames.
int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    auto table=cuHEpp::TableGen<10>();
    auto twist=cuHEpp::TwistGen<10>();
    std::mt19937_64 rng(0x5347454e484f4745ULL);
    std::vector<Frame> inputs(8), expected(8);
    for (int f=0; f<8; ++f) {
        for (int i=0; i<1024; ++i) inputs[f][i]=cuHEpp::INTorus(rng());
        expected[f]=inputs[f];
        cuHEpp::NTT<10,5>(expected[f],(*table)[0]);
        for (int i=0; i<1024; ++i) expected[f][i]*=(*twist)[0][i]*cuHEpp::InvPow2(10);
    }
    int checked=0;
    for (int gap : {0,1,3,31,32,33}) for (int abort_cycle : {1,17,31,45,72}) {
        VNTTWrap dut; reset(dut);
        // Abort while a frame is entering / resident / reaching its output.
        {
            dut.io_enable=1;
            for (int c=0; c<abort_cycle; ++c) tick(dut);
            reset(dut);
        }
        int out_frame=0, out_cycle=0, last_start=-1;
        for (int c=0; c<2000; ++c) {
            const int f=c/(32+gap), lane_cycle=c%(32+gap);
            dut.io_enable=f<8 && lane_cycle<32;
            if (dut.io_enable) {
                if (!dut.io_ready) { std::cerr<<"input not ready\n"; return 1; }
                for (int lane=0; lane<32; ++lane) {
                    uint64_t v=inputs[f][lane_cycle*32+lane].value;
                    dut.io_in[2*lane]=uint32_t(v); dut.io_in[2*lane+1]=uint32_t(v>>32);
                }
            }
            tick(dut);
            if (!dut.io_validout) {
                if (out_cycle) { std::cerr<<"output gap inside frame\n"; return 1; }
                continue;
            }
            if (out_frame>=8) { std::cerr<<"unexpected output after final frame\n"; return 1; }
            if (!out_cycle) {
                if (last_start>=0 && c-last_start!=32+gap) {
                    std::cerr<<"frame interval mismatch gap="<<gap<<" interval="<<c-last_start<<'\n'; return 1;
                }
                last_start=c;
            }
            for (int lane=0; lane<32; ++lane) {
                uint64_t got=uint64_t(dut.io_out[2*lane]) | (uint64_t(dut.io_out[2*lane+1])<<32);
                uint64_t want=expected[out_frame][out_cycle*32+lane].value;
                if (got!=want) {
                    std::cerr<<"mismatch gap="<<gap<<" frame="<<out_frame<<" cycle="<<out_cycle<<" lane="<<lane<<'\n'; return 1;
                }
            }
            if (++out_cycle==32) { out_cycle=0; ++out_frame; }
        }
        if (out_frame!=8) { std::cerr<<"missing output frame\n"; return 1; }
        checked+=out_frame;
        dut.final();
    }
    std::cout<<"PASS hoge_streaming_ntt_overlap_test frames="<<checked<<" saturated_interval=32\n";
}
