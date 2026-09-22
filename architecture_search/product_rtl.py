"""Counted frame adapters and three-engine product composition.

External streams use two packed little-lane-first elements per beat. Fixed-rate
cores never see a mid-frame stall; every launch reserves a full output frame.
"""
import math
from .products import output_width


def frame_engine(name, core, meta, width, input_n=None, external_lanes=2):
    n=meta['transform_size']; k=meta['streaming_width']; t=n//k
    input_n=input_n or n
    rv=meta.get('protocol')=='ready-valid'
    ready=meta.get('has_ready',False)
    offset=meta.get('next_offset',0); data_at=max(0,-offset); token_at=max(0,offset)
    ii=meta['initiation_interval']; warmup=(meta['latency']+t+abs(offset)+4) if meta.get('schema')=='sgen-search-v1' else 0; depth=max(2,math.ceil((meta['latency']+t)/ii)+1)
    declarations='\n'.join(f'wire [{width-1}:0] ci{j},co{j}; assign ci{j}=input_mem[read_bank*N+(feed_age-DATA_AT)*K+{j}];' for j in range(k))
    ports=','.join(f'.i{j}(ci{j}),.o{j}(co{j})' for j in range(k))
    if rv:
        control='.in_valid(feed_data),.in_ready(core_ready),.out_valid(core_out),.out_ready(1\'b1)'
        capture_condition='core_out'; capture_index='capture_beat'
    else:
        control='.next(feed_token),.next_out(core_out)'+(',.ready(core_ready)' if ready else '')
        capture_condition='core_out || capturing'; capture_index='(core_out ? 0 : capture_beat)'
    clock='clk' if meta.get('schema')=='sgen-search-v1' else 'clock'
    capture='\n'.join(f'output_mem[capture_bank*N+capture_index*K+{j}]<=co{j};' for j in range(k))
    e=external_lanes
    capture_input='\n'.join(f'input_mem[write_bank*N+input_beat*{e}+{j}]<=in_data[{j*width} +: {width}];' for j in range(e))
    output_pack=','.join(f'output_mem[output_bank*N+output_beat*{e}+{j}]' for j in reversed(range(e)))
    return f'''
module {name}(input clock,reset,input in_valid,output in_ready,input [{e*width-1}:0] in_data,
output out_valid,input out_ready,output [{e*width-1}:0] out_data);
localparam N={n}, IN_N={input_n}, K={k}, T={t}, W={width}, DEPTH={depth}, DATA_AT={data_at}, TOKEN_AT={token_at};
reg [W-1:0] input_mem[0:2*N-1],output_mem[0:DEPTH*N-1];
reg [1:0] input_full; reg [DEPTH-1:0] output_full;
integer write_bank,read_bank,input_beat,output_bank,output_beat,capture_bank,capture_beat;
integer reservations,cooldown,feed_age,j,initializing;
wire core_reset=reset || initializing>0;
reg feeding,capturing;
wire core_ready,core_out;
{'assign core_ready=1;' if not rv and not ready else ''}
wire feed_data=feeding && feed_age>=DATA_AT && feed_age<DATA_AT+T;
wire feed_token=feeding && feed_age==TOKEN_AT;
wire launch=!feeding && input_full[read_bank] && reservations<DEPTH && cooldown==0 && core_ready;
wire drain=out_valid && out_ready && output_beat==N/{e}-1;
wire capture_event={capture_condition};
wire [31:0] capture_index={capture_index};
assign in_ready=!input_full[write_bank] && initializing==0;
assign out_valid=output_full[output_bank];
assign out_data={{{output_pack}}};
{declarations}
{core} core(.{clock}(clock),.reset(core_reset),{control},{ports});
always @(posedge clock) begin
 if(reset) begin
  input_full<=0;output_full<=0;write_bank<=0;read_bank<=0;input_beat<=0;output_bank<=0;output_beat<=0;
  capture_bank<=0;capture_beat<=0;reservations<=0;cooldown<=0;feed_age<=0;feeding<=0;capturing<=0;initializing<={warmup};
 end else if(initializing>0)begin initializing<=initializing-1;end
 else begin
  if(cooldown>0)cooldown<=cooldown-1;
  case ({{launch,drain}}) 2'b10:reservations<=reservations+1;2'b01:reservations<=reservations-1;default:;endcase
  if(in_valid && in_ready) begin
   {capture_input}
   if(input_beat==IN_N/{e}-1) begin
    for(j=IN_N;j<N;j=j+1)input_mem[write_bank*N+j]<=0;
    input_full[write_bank]<=1;write_bank<=1-write_bank;input_beat<=0;
   end else input_beat<=input_beat+1;
  end
  if(launch) begin feeding<=1;feed_age<=0;cooldown<={ii-1};end
  else if(feeding) begin
   if(feed_age>=DATA_AT+T-1 && feed_age>=TOKEN_AT) begin
    feeding<=0;input_full[read_bank]<=0;read_bank<=1-read_bank;
   end else feed_age<=feed_age+1;
  end
  if(capture_event) begin
   {capture}
   if(capture_index==T-1) begin
    output_full[capture_bank]<=1;capture_bank<=(capture_bank==DEPTH-1?0:capture_bank+1);
    capture_beat<=0;capturing<=0;
   end else begin capture_beat<=capture_index+1;capturing<=1;end
  end
  if(out_valid && out_ready) begin
   if(drain) begin output_full[output_bank]<=0;output_bank<=(output_bank==DEPTH-1?0:output_bank+1);output_beat<=0;end
   else output_beat<=output_beat+1;
  end
 end
end
endmodule
'''


def multiply_module(width, fft, frac):
    # Three elastic arithmetic stages. Gating the whole pipeline keeps tokens
    # aligned and makes both forward streams consume a beat atomically.
    scalar=width//2 if fft else width
    declarations=[]; stage1=[]; stage2=[]; stage3=[]; assigns=[]
    for lane in range(2):
        if fft:
            d=scalar
            for part in ('rr','ii','ri','ir'):
                declarations.append(f'reg signed [{2*d-1}:0] {part}{lane};')
                ai=lane*width+(d if part[0]=='i' else 0); bi=lane*width+(d if part[1]=='i' else 0)
                stage1.append(f'{part}{lane} <= $signed(a[{ai} +: {d}]) * $signed(b[{bi} +: {d}]);')
            declarations.append(f'reg signed [{d}:0] re{lane},im{lane}; reg [{width-1}:0] value{lane};')
            stage2.extend([f're{lane} <= $signed(rr{lane}[{frac} +: {d}]) - $signed(ii{lane}[{frac} +: {d}]);',
                           f'im{lane} <= $signed(ri{lane}[{frac} +: {d}]) + $signed(ir{lane}[{frac} +: {d}]);'])
            stage3.append(f'value{lane} <= {{im{lane}[{d-1}:0],re{lane}[{d-1}:0]}};')
        else:
            declarations.append(f'reg [33:0] p{lane};reg signed [18:0] diff{lane};reg [16:0] value{lane};')
            stage1.append(f'p{lane}<=a[{lane*17} +: 17]*b[{lane*17} +: 17];')
            stage2.append(f'diff{lane}<=$signed({{3\'b0,p{lane}[15:0]}})-$signed({{1\'b0,p{lane}[33:16]}});')
            stage3.append(f'value{lane}<=diff{lane}<0?diff{lane}+19\'d65537:diff{lane};')
        assigns.append(f'assign out_data[{lane*width} +: {width}]=value{lane};')
    return f'''
module ProductMultiply(input clock,reset,input a_valid,b_valid,output a_ready,b_ready,
input [{2*width-1}:0] a,b,output out_valid,input out_ready,output [{2*width-1}:0] out_data);
reg [2:0] valid;
wire advance=!valid[2] || out_ready;
assign a_ready=advance && b_valid;assign b_ready=advance && a_valid;assign out_valid=valid[2];
{''.join(declarations)}
{''.join(assigns)}
always @(posedge clock) begin
 if(reset)valid<=0;
 else if(advance) begin
  valid<={{valid[1:0],a_valid && b_valid}};
  {''.join(stage1)}
  {''.join(stage2)}
  {''.join(stage3)}
 end
end
endmodule
'''


def fold_module(n, scalar, frac, outwidth):
    shift=frac+(2*n).bit_length()-1
    return f'''
module ProductFold(input clock,reset,input in_valid,output in_ready,input [{4*scalar-1}:0] in_data,
output out_valid,input out_ready,output [{2*outwidth-1}:0] out_data);
localparam N={n},W={scalar},OW={outwidth},SHIFT={shift};
reg signed [W-1:0] low[0:N-1];reg [OW-1:0] result[0:2*N-1];
reg [1:0] full;integer write_bank,read_bank,beat,outbeat,j;
function automatic [OW-1:0] rounded(input signed [W:0] v);
 reg signed [W:0] base;reg [SHIFT-1:0] rem;
 begin base=v>>>SHIFT;rem=v[SHIFT-1:0];
 if(rem>{{1'b1,{{(SHIFT-1){{1'b0}}}}}} || (rem=={{1'b1,{{(SHIFT-1){{1'b0}}}}}} && base[0]))base=base+1;
 rounded=base[OW-1:0];end
endfunction
assign in_ready=!full[write_bank];assign out_valid=full[read_bank];
assign out_data={{result[read_bank*N+outbeat*2+1],result[read_bank*N+outbeat*2]}};
always @(posedge clock)begin
 if(reset)begin full<=0;write_bank<=0;read_bank<=0;beat<=0;outbeat<=0;end
 else begin
  if(in_valid && in_ready)begin
   for(j=0;j<2;j=j+1)begin
    if(beat<N/2)low[beat*2+j]<=in_data[j*2*W +: W];
    else result[write_bank*N+(beat-N/2)*2+j]<=rounded($signed({{low[(beat-N/2)*2+j][W-1],low[(beat-N/2)*2+j]}})-$signed({{in_data[j*2*W+W-1],in_data[j*2*W +: W]}}));
   end
   if(beat==N-1)begin beat<=0;full[write_bank]<=1;write_bank<=1-write_bank;end
   else beat<=beat+1;
  end
  if(out_valid && out_ready)begin
   if(outbeat==N/2-1)begin full[read_bank]<=0;read_bank<=1-read_bank;outbeat<=0;end else outbeat<=outbeat+1;
  end
 end
end
endmodule
'''


def compose(w,c,forward,inverse):
    fft=c['generator']=='sgen'; scalar=c['integer_bits']+c['fractional_bits'] if fft else 17
    width=2*scalar if fft else scalar; ow=output_width(w); frac=c.get('fractional_bits',0)
    pieces=[frame_engine('ForwardFrame','ProductForward',forward,width,w['n']),
            frame_engine('InverseFrame','ProductInverse',inverse,width),multiply_module(width,fft,frac)]
    if fft:pieces.append(fold_module(w['n'],scalar,frac,ow))
    inputs=[];outputs=[]
    for lane in range(2):
        for op in ('a','b'):
            if fft:
                value=f"{{{{{scalar-4}{{{op}[{lane*4+3}]}}}},{op}[{lane*4} +: 4]}} << {frac}"
                inputs.append(f'wire [{scalar-1}:0] {op}q{lane}={value};assign {op}_data[{lane*width} +: {width}]={{{scalar}\'b0,{op}q{lane}}};')
            else:
                inputs.append(f'wire signed [17:0] {op}q{lane}=$signed({op}[{lane*4} +: 4]);assign {op}_data[{lane*17} +: 17]={op}q{lane}<0?{op}q{lane}+18\'d65537:{op}q{lane};')
        if not fft:
            outputs.append(f'wire signed [17:0] centered{lane}={{1\'b0,iv_data[{lane*17} +: 17]}}>18\'d32768 ? $signed({{1\'b0,iv_data[{lane*17} +: 17]}})-18\'sd65537:$signed({{1\'b0,iv_data[{lane*17} +: 17]}});assign out_data[{lane*ow} +: {ow}]=centered{lane};')
    pieces.append(f'''
module SearchTop(input clock,reset,input in_valid,output in_ready,input [7:0] a,b,
output out_valid,input out_ready,output [{2*ow-1}:0] out_data);
wire ar,br,av,bv,am,bm,mv,mr,iv,ir;
wire [{2*width-1}:0] a_data,b_data,fa,fb,product,iv_data;
{''.join(inputs)}
assign in_ready=ar && br;
ForwardFrame f_a(clock,reset,in_valid && br,ar,a_data,av,am,fa);
ForwardFrame f_b(clock,reset,in_valid && ar,br,b_data,bv,bm,fb);
ProductMultiply pointwise(clock,reset,av,bv,am,bm,fa,fb,mv,mr,product);
InverseFrame inverse(clock,reset,mv,mr,product,iv,ir,iv_data);
{'ProductFold fold(clock,reset,iv,ir,iv_data,out_valid,out_ready,out_data);' if fft else 'assign out_valid=iv;assign ir=out_ready;'+''.join(outputs)}
endmodule
''')
    return '\n'.join(pieces)
