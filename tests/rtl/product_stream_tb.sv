module SearchTop(input clock,reset,in_valid,output in_ready,input [7:0] a,b,
                 output out_valid,input out_ready,output [7:0] out_data);
reg valid;reg [7:0] data;
assign in_ready=!valid || out_ready;assign out_valid=valid;assign out_data=data;
always @(posedge clock)if(reset)valid<=0;else if(in_ready)begin valid<=in_valid;data<=a^b;end
endmodule

module test;
reg clock=0,reset_n=0;always #5 clock=~clock;
reg [31:0] input_data;reg input_valid,output_ready;
wire input_ready,output_valid,output_last;wire [63:0] output_data;wire [7:0] keep,strb;
ProductStream #(.N(8),.OW(4)) dut(clock,reset_n,input_data,4'hf,4'hf,1'b0,input_valid,input_ready,
                                output_data,keep,strb,output_last,output_valid,output_ready);
integer batch,sent,received,cycle,first,last,stalls_in,stalls_out;
reg held_valid;reg [63:0] held;
initial begin
 input_valid=0;output_ready=0;input_data=0;held_valid=0;
 repeat(3)@(negedge clock);reset_n=1;
 for(batch=0;batch<3;batch=batch+1)begin
  sent=0;received=0;first=-1;last=-1;stalls_in=0;stalls_out=0;
  for(cycle=0;cycle<1000 && received<13;cycle=cycle+1)begin
   input_valid=sent<8;
   input_data=((sent==0)<<16)|((sent==7)<<17)|(sent+batch);
   output_ready=cycle%7<4;
   @(posedge clock);
   if(held_valid && (!output_valid || held!==output_data))$fatal(1,"unstable board stream");
   held_valid=output_valid && !output_ready;held=output_data;
   if(first>=0 && sent<8 && input_valid && !input_ready)stalls_in=stalls_in+1;
   if(first>=0 && received<8 && output_valid && !output_ready)stalls_out=stalls_out+1;
   if(input_valid && input_ready)begin if(sent==0)first=cycle;sent=sent+1;end
   if(output_valid && output_ready)begin
    if(keep!==8'hff || strb!==8'hff)$fatal(1,"invalid byte enables");
    if(received<8)begin
     if(output_data!==received+batch)$fatal(1,"board output order");
     if(received==7)last=cycle;
    end else begin
     if(output_data[63:56]!==received-7)$fatal(1,"telemetry tag");
     case(received)
      8:if(output_data[55:0]!==last-first)$fatal(1,"cycle counter");
      9,10:if(output_data[55:0]!==2)$fatal(1,"product counter");
      11:if(output_data[55:0]!==stalls_in)$fatal(1,"source stall counter");
      12:if(output_data[55:0]!==stalls_out)$fatal(1,"sink stall counter");
     endcase
    end
    if(output_last!==(received==12))$fatal(1,"last marker");
    received=received+1;
   end
   @(negedge clock);
  end
  if(sent!=8 || received!=13)$fatal(1,"board watchdog");
 end
 $display("PASS board stream batches/counters/backpressure");$finish;
end
endmodule
