#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>

extern "C" void product_source(const ap_uint<8>* a, const ap_uint<8>* b,
                                hls::stream<ap_axiu<32,0,0,0>>& output,
                                unsigned beats) {
#pragma HLS INTERFACE m_axi port=a offset=slave bundle=gmem0
#pragma HLS INTERFACE m_axi port=b offset=slave bundle=gmem1
#pragma HLS INTERFACE axis port=output
#pragma HLS INTERFACE s_axilite port=a bundle=control
#pragma HLS INTERFACE s_axilite port=b bundle=control
#pragma HLS INTERFACE s_axilite port=beats bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    for (unsigned i=0; i<beats; ++i) {
#pragma HLS PIPELINE II=1
        ap_axiu<32,0,0,0> word;
        word.data=0;word.data.range(7,0)=a[i];word.data.range(15,8)=b[i];
        word.data[16]=(i==0);word.data[17]=(i+1==beats);
        word.keep=-1;word.strb=-1;word.last=(i+1==beats);
        output.write(word);
    }
}

extern "C" void product_sink(hls::stream<ap_axiu<64,0,0,0>>& input,
                              ap_uint<64>* output,unsigned beats) {
#pragma HLS INTERFACE axis port=input
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem2
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=beats bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    for(unsigned i=0;i<beats+5;++i) {
#pragma HLS PIPELINE II=1
        output[i]=input.read().data;
    }
}
