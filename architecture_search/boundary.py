"""One elastic input register and one elastic output register for generic cores."""

def registered_ready_valid(text: str, lanes: int, width: int) -> str:
    if text.count('module SearchTop(')!=1:
        raise ValueError('expected one SearchTop declaration')
    core=text.replace('module SearchTop(', 'module SearchCore(',1)
    ports=',\n'.join(f'input [{width-1}:0] i{k}, output [{width-1}:0] o{k}' for k in range(lanes))
    signals='\n'.join(f'reg [{width-1}:0] input_{k},output_{k}; wire [{width-1}:0] core_o{k}; assign o{k}=output_{k};' for k in range(lanes))
    connections=','.join(f'.i{k}(input_{k}),.o{k}(core_o{k})' for k in range(lanes))
    capture_in=' '.join(f'input_{k}<=i{k};' for k in range(lanes))
    capture_out=' '.join(f'output_{k}<=core_o{k};' for k in range(lanes))
    return core+f'''
// Benchmark boundary: two elastic register stages; included in measured latency and resources.
module SearchTop(input clock,reset,in_valid,output in_ready,output out_valid,input out_ready,
{ports});
reg input_full,output_full;
wire core_ready,core_valid;
wire take_output=!output_full || out_ready;
assign in_ready=!input_full || core_ready;
assign out_valid=output_full;
{signals}
SearchCore core(.clock(clock),.reset(reset),.in_valid(input_full),.in_ready(core_ready),.out_valid(core_valid),.out_ready(take_output),{connections});
always @(posedge clock) begin
 if(reset) begin input_full<=0; output_full<=0; end
 else begin
  if(in_ready) begin input_full<=in_valid; if(in_valid) begin {capture_in} end end
  if(take_output) begin output_full<=core_valid; if(core_valid) begin {capture_out} end end
 end
end
endmodule
'''
