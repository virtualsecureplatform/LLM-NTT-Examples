// Two packed signed four-bit coefficients per operand. Batch markers are
// carried in input bits 16 (first beat) and 17 (last beat).
module ProductStream #(
  parameter integer N=64, parameter integer OW=13
)(input ap_clk,ap_rst_n,
  input [31:0] s_axis_tdata,input [3:0] s_axis_tkeep,s_axis_tstrb,
  input s_axis_tlast,s_axis_tvalid,output s_axis_tready,
  output reg [63:0] m_axis_tdata,output [7:0] m_axis_tkeep,m_axis_tstrb,
  output m_axis_tlast,m_axis_tvalid,input m_axis_tready);
wire core_ready,core_valid;wire [2*OW-1:0] core_data;
reg active,last_seen;reg [2:0] trailer;
reg [55:0] cycles,elapsed,input_beats,output_beats,input_stalls,output_stalls;
wire [55:0] accepted_products=input_beats/(N/2),completed_products=output_beats/(N/2);
wire input_fire=s_axis_tvalid && s_axis_tready;
wire output_fire=core_valid && m_axis_tready && trailer==0;
assign s_axis_tready=core_ready && trailer==0 && !last_seen;
assign m_axis_tvalid=trailer!=0 || core_valid;
assign m_axis_tkeep=8'hff;assign m_axis_tstrb=8'hff;
assign m_axis_tlast=trailer==5;
SearchTop product(ap_clk,!ap_rst_n,s_axis_tvalid && trailer==0 && !last_seen,
                  core_ready,s_axis_tdata[7:0],s_axis_tdata[15:8],
                  core_valid,m_axis_tready && trailer==0,core_data);
always @(*)begin
 m_axis_tdata={{(64-2*OW){1'b0}},core_data};
 case(trailer)
  1:m_axis_tdata={8'd1,elapsed};
  2:m_axis_tdata={8'd2,accepted_products};
  3:m_axis_tdata={8'd3,completed_products};
  4:m_axis_tdata={8'd4,input_stalls};
  5:m_axis_tdata={8'd5,output_stalls};
 endcase
end
always @(posedge ap_clk)begin
 if(!ap_rst_n)begin
  active<=0;last_seen<=0;trailer<=0;cycles<=0;elapsed<=0;
  input_beats<=0;output_beats<=0;input_stalls<=0;output_stalls<=0;
 end else begin
  if(active)cycles<=cycles+1;
  if(active && s_axis_tvalid && !s_axis_tready && !last_seen)input_stalls<=input_stalls+1;
  if(active && core_valid && !m_axis_tready)output_stalls<=output_stalls+1;
  if(input_fire)begin
   if(s_axis_tdata[16])begin
    active<=1;cycles<=0;input_beats<=1;output_beats<=0;
    input_stalls<=0;output_stalls<=0;
   end else input_beats<=input_beats+1;
   if(s_axis_tdata[17])last_seen<=1;
  end
  if(output_fire)begin
   output_beats<=output_beats+1;
   if(last_seen && output_beats+1==input_beats)begin
    elapsed<=cycles+1;active<=0;trailer<=1;
   end
  end
  if(trailer!=0 && m_axis_tready)begin
   if(trailer==5)begin trailer<=0;last_seen<=0;end else trailer<=trailer+1;
  end
 end
end
endmodule
