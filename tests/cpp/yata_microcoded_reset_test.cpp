// Reuse the unchanged arithmetic oracle and port helpers; add mid-operation reset.
#define main original_yata_reference_main
#include "small_yata_reference_test.cpp"
#undef main

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    auto table=raintt::TableGen<kNbit>();
    auto twist=raintt::TwistGen<kNbit,3>();
    std::array<uint32_t,kN> input{};
    for(int i=0;i<kN;++i) input[i]=(7919U*i+12345U)%uint32_t(kP);
    std::array<raintt::DoubleSWord,kN> expected_intt{};
    raintt::TwistINTT<uint32_t,kNbit,false>(expected_intt,input,(*table)[1],(*twist)[1]);
    std::array<uint32_t,kN> expected_ntt{};
    auto ntt_input=expected_intt;
    expected_yata_ntt(expected_ntt,ntt_input,(*table)[0],(*twist)[0]);
    std::array<int32_t,kN> words{};
    for(int i=0;i<kN;++i) words[i]=int32_t(expected_intt[i]);
    int checks=0;
    for(int direction : {0,1}) for(int abort_cycle : {1,8,9,10,11,12,13,14,15,16,39,150,430}) {
        Dut dut; reset(dut);
        for(int c=0;c<abort_cycle;++c) {
            dut.io_intt_validin=direction==0 && c<kCycles;
            dut.io_ntt_validin=direction==1 && c<kCycles;
            for(int lane=0;lane<kLanes;++lane) {
                intt_in(dut,lane)=input[(lane*kCycles+c)%kN];
                ntt_in(dut,lane)=pack_sint27(words[(c*kLanes+lane)%kN]);
            }
            tick(dut);
        }
        reset(dut);
        if(dut.io_intt_validout || dut.io_ntt_validout) return 1;
        int wait=0;
        if(direction==1) {
            std::array<int32_t,kN> got{};
            if(!run_intt(dut,input,got,wait)) return 1;
            for(int i=0;i<kN;++i) if(!same_mod_p(got[i],int32_t(expected_intt[i]))) {
                std::cerr<<"INTT mismatch after reset at "<<abort_cycle<<" index "<<i<<"\n";return 1;
            }
        } else {
            std::array<uint32_t,kN> got{};
            if(!run_ntt(dut,words,got,wait)) return 1;
            if(got!=expected_ntt) {std::cerr<<"NTT mismatch after reset at "<<abort_cycle<<"\n";return 1;}
        }
        for(int c=0;c<16;++c) {tick(dut);if(dut.io_intt_validout || dut.io_ntt_validout) return 1;}
        ++checks;
    }
    std::cout<<"PASS yata_microcoded_reset_test checks="<<checks<<"\n";
}
