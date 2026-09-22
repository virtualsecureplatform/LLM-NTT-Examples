// XRT 2023.2 host: every measured and warm-up product is checked independently.
#include <xrt/xrt_bo.h>
#include <xrt/xrt_device.h>
#include <xrt/xrt_kernel.h>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <random>
#include <stdexcept>
#include <vector>

int main(int argc,char**argv) try {
    if(argc!=5)throw std::runtime_error("usage: product_host XCLBIN OUTPUT.json OUTPUT_WIDTH CLOCK_MHZ");
    const unsigned ow=std::stoul(argv[3]);const double mhz=std::stod(argv[4]);
    if(ow<13||ow>31||mhz<=0)throw std::runtime_error("invalid width or clock");
    xrt::device device(0);auto uuid=device.load_xclbin(argv[1]);
    xrt::kernel source(device,uuid,"product_source"),sink(device,uuid,"product_sink");
    std::ofstream report(argv[2]);if(!report)throw std::runtime_error("cannot create report");report<<std::setprecision(17);report<<"{\"schema\":\"product-board-v1\",\"n\":64,\"clock_mhz\":"<<mhz<<",\"trials\":[";
    bool comma=false;
    for(unsigned batch:{1u,16u,256u,4096u}) {
        const unsigned beats=batch*32;
        xrt::bo a(device,beats,source.group_id(0)),b(device,beats,source.group_id(1));
        xrt::bo output(device,(beats+5)*8,sink.group_id(1));
        auto pa=a.map<uint8_t*>();auto pb=b.map<uint8_t*>();auto po=output.map<uint64_t*>();
        std::vector<std::array<int,64>> expected(batch);
        for(unsigned repeat=0;repeat<12;++repeat) {
            const unsigned seed=20260922+batch*17+repeat;std::mt19937 rng(seed);
            for(unsigned frame=0;frame<batch;++frame) {
                std::array<int,64> av,bv;expected[frame].fill(0);
                for(unsigned j=0;j<64;++j){av[j]=int(rng()%15)-7;bv[j]=int(rng()%15)-7;}
                for(unsigned j=0;j<32;++j){pa[frame*32+j]=(av[2*j]&15)|((av[2*j+1]&15)<<4);pb[frame*32+j]=(bv[2*j]&15)|((bv[2*j+1]&15)<<4);}
                for(unsigned i=0;i<64;++i)for(unsigned j=0;j<64;++j)
                    expected[frame][(i+j)%64]+=(i+j<64?1:-1)*av[i]*bv[j];
            }
            xrt::run send(source),receive(sink);
            send.set_arg(0,a);send.set_arg(1,b);send.set_arg(3,beats);
            receive.set_arg(1,output);receive.set_arg(2,beats);
            const auto start=std::chrono::steady_clock::now();
            a.sync(XCL_BO_SYNC_BO_TO_DEVICE);b.sync(XCL_BO_SYNC_BO_TO_DEVICE);
            receive.start();send.start();send.wait();receive.wait();output.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
            const auto end=std::chrono::steady_clock::now();
            for(unsigned frame=0;frame<batch;++frame)for(unsigned j=0;j<64;++j) {
                uint32_t raw=(po[frame*32+j/2]>>((j%2)*ow))&((uint64_t(1)<<ow)-1);
                int32_t value=(raw&(uint32_t(1)<<(ow-1)))?int64_t(raw)-(int64_t(1)<<ow):raw;
                if(value!=expected[frame][j])throw std::runtime_error("coefficient mismatch frame "+std::to_string(frame)+" coefficient "+std::to_string(j));
            }
            uint64_t counters[5];for(unsigned j=0;j<5;++j){
                if(po[beats+j]>>56!=j+1)throw std::runtime_error("counter trailer tag mismatch");
                counters[j]=po[beats+j]&((uint64_t(1)<<56)-1);
            }
            if(counters[1]!=batch||counters[2]!=batch||!counters[0])throw std::runtime_error("counter mismatch");
            if(comma)report<<',';comma=true;
            report<<"{\"batch\":"<<batch<<",\"repeat\":"<<repeat<<",\"warmup\":"<<(repeat<2?"true":"false")
                  <<",\"seed\":"<<seed<<",\"checked_coefficients\":"<<batch*64<<",\"kernel_cycles\":"<<counters[0]
                  <<",\"kernel_seconds\":"<<counters[0]/(mhz*1e6)<<",\"transfer_inclusive_seconds\":"<<std::chrono::duration<double>(end-start).count()
                  <<",\"accepted_products\":"<<counters[1]<<",\"completed_products\":"<<counters[2]
                  <<",\"input_stall_cycles\":"<<counters[3]<<",\"output_stall_cycles\":"<<counters[4]
                  <<",\"host_to_device_bytes\":"<<2*beats<<",\"device_to_host_bytes\":"<<8*(beats+5)<<'}';
            report.flush();
        }
    }
    report<<"],\"passed\":true}\n";
    return 0;
} catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
