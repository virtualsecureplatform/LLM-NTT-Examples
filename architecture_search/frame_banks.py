"""Single-write physical banks for power-of-two internal/external lane ratios."""
import math


def emit(name,core,meta,width,input_n=None,external_lanes=2,registered_output=False):
    n=meta['transform_size'];k=meta['streaming_width'];e=external_lanes;b=max(k,e)
    input_n=input_n or n
    if any(x<1 or x&(x-1) for x in (n,k,e)) or n%b or input_n%e or not 0<input_n<=n:
        raise ValueError('banked frames require aligned power-of-two lane widths')
    t=n//k;rv=meta.get('protocol')=='ready-valid';ready=meta.get('has_ready',False)
    offset=meta.get('next_offset',0);data_at=max(0,-offset);token_at=max(0,offset)
    ii=meta['initiation_interval'];depth=max(2,math.ceil((meta['latency']+t)/ii)+1)
    warmup=meta['latency']+t+abs(offset)+4 if meta.get('schema')=='sgen-search-v1' else 0
    nr=n//b;in_ratio=b//e;core_ratio=b//k
    memories='\n'.join(f'reg [W-1:0] input_bank{i}[0:{2*nr-1}],output_bank{i}[0:{depth*nr-1}];' for i in range(b))
    # One syntactic write per bank. Padding and capture use the same port.
    capture_input='\n'.join(f'''if(input_beat % {in_ratio} == {i//e})
input_bank{i}[write_bank*{nr}+input_beat/{in_ratio}] <= padding ? {width}'d0 : in_data[{(i%e)*width} +: {width}];''' for i in range(b))
    capture='\n'.join(f'''if(capture_index % {core_ratio} == {i//k})
output_bank{i}[capture_bank*{nr}+capture_index/{core_ratio}] <= co{i%k};''' for i in range(b))
    def select(bank_names,lane,lanes,ratio,index):
        options=[f'{bank_names}{j*lanes+lane}[{index}]' for j in range(ratio)]
        return ''.join(f'(({("feed_age-DATA_AT" if bank_names=="input_bank" else "output_beat")}) % {ratio} == {j}) ? {value} : ' for j,value in enumerate(options[:-1]))+options[-1]
    declarations='\n'.join(f'wire [{width-1}:0] ci{j},co{j}; assign ci{j}='+select('input_bank',j,k,core_ratio,f'read_bank*{nr}+(feed_age-DATA_AT)/{core_ratio}')+';' for j in range(k))
    output_pack=','.join(select('output_bank',j,e,in_ratio,f'output_bank*{nr}+output_beat/{in_ratio}') for j in reversed(range(e)))
    ports=','.join(f'.i{j}(ci{j}),.o{j}(co{j})' for j in range(k))
    control=".in_valid(feed_data),.in_ready(core_ready),.out_valid(core_out),.out_ready(1'b1)" if rv else '.next(feed_token),.next_out(core_out)'+(',.ready(core_ready)' if ready else '')
    condition='core_out' if rv else 'core_out || capturing';index='capture_beat' if rv else '(core_out ? 0 : capture_beat)'
    clock='clk' if meta.get('schema')=='sgen-search-v1' else 'clock'
    def bits(value):return max(1,(value-1).bit_length())
    consume='frame_valid && frame_ready' if registered_output else 'out_valid && out_ready'
    output_wiring=f'assign out_valid=output_full[output_bank];assign out_data={{{output_pack}}};'
    output_reset=output_update=''
    if registered_output:
        output_wiring=f'''reg output_valid;reg [{e*width-1}:0] output_data;
wire frame_valid=output_full[output_bank];wire frame_ready=!output_valid || out_ready;
assign out_valid=output_valid;assign out_data=output_data;
wire [{e*width-1}:0] frame_data={{{output_pack}}};'''
        output_reset='output_valid<=0;'
        output_update='if(frame_ready)begin output_valid<=frame_valid;if(frame_valid)output_data<=frame_data;end\n'
    return f'''module {name}(input clock,reset,in_valid,output in_ready,input [{e*width-1}:0] in_data,
output out_valid,input out_ready,output [{e*width-1}:0] out_data);
localparam N={n},IN_N={input_n},K={k},T={t},W={width},DEPTH={depth},DATA_AT={data_at},TOKEN_AT={token_at};
{memories}
reg [1:0] input_full;reg [DEPTH-1:0] output_full;
reg write_bank,read_bank;reg [{bits(n//e)-1}:0] input_beat,output_beat;
reg [{bits(depth)-1}:0] output_bank,capture_bank;reg [{bits(t)-1}:0] capture_beat;
reg [{bits(depth+1)-1}:0] reservations;reg [{bits(ii+1)-1}:0] cooldown;
reg [{bits(max(data_at+t,token_at+1)+1)-1}:0] feed_age;
reg [{bits(warmup+1)-1}:0] initializing;reg feeding,capturing,padding;
wire core_reset=reset || initializing>0;wire core_ready,core_out;
{'assign core_ready=1;' if not rv and not ready else ''}
wire feed_data=feeding && feed_age>=DATA_AT && feed_age<DATA_AT+T;
wire feed_token=feeding && feed_age==TOKEN_AT;
wire launch=!feeding && input_full[read_bank] && reservations<DEPTH && cooldown==0 && core_ready;
wire drain={consume} && output_beat==N/{e}-1;
wire capture_event={condition};wire [{bits(t)-1}:0] capture_index={index};
assign in_ready=!input_full[write_bank] && initializing==0 && !padding;
{output_wiring}
{declarations}
{core} core(.{clock}(clock),.reset(core_reset),{control},{ports});
always @(posedge clock)begin
if(reset)begin
input_full<=0;output_full<=0;write_bank<=0;read_bank<=0;input_beat<=0;output_bank<=0;output_beat<=0;
capture_bank<=0;capture_beat<=0;reservations<=0;cooldown<=0;feed_age<=0;feeding<=0;capturing<=0;initializing<={warmup};padding<=0;{output_reset}
end else if(initializing>0)initializing<=initializing-1;
else begin
{output_update}if(cooldown>0)cooldown<=cooldown-1;
case({{launch,drain}})2'b10:reservations<=reservations+1;2'b01:reservations<=reservations-1;default:;endcase
if((in_valid && in_ready) || padding)begin
{capture_input}
if(input_beat==N/{e}-1)begin input_full[write_bank]<=1;write_bank<=1-write_bank;input_beat<=0;padding<=0;end
else begin
input_beat<=input_beat+1;
if(input_beat==IN_N/{e}-1)padding<=1;
end
end
if(launch)begin feeding<=1;feed_age<=0;cooldown<={ii-1};end
else if(feeding)begin
if(feed_age>=DATA_AT+T-1 && feed_age>=TOKEN_AT)begin feeding<=0;input_full[read_bank]<=0;read_bank<=1-read_bank;end
else feed_age<=feed_age+1;
end
if(capture_event)begin
{capture}
if(capture_index==T-1)begin output_full[capture_bank]<=1;capture_bank<=(capture_bank==DEPTH-1?0:capture_bank+1);capture_beat<=0;capturing<=0;end
else begin capture_beat<=capture_index+1;capturing<=1;end
end
if({consume})begin
if(drain)begin output_full[output_bank]<=0;output_bank<=(output_bank==DEPTH-1?0:output_bank+1);output_beat<=0;end
else output_beat<=output_beat+1;
end
end
end
endmodule'''
