"""Counted dual-direction NGen storage/control boundary for transform research."""
import re
from . import oracle


def namespace(text,prefix):
    names=re.findall(r'\bmodule\s+(\w+)',text)
    if 'SearchTop' not in names:raise ValueError('missing stream core')
    for name in sorted(names,key=len,reverse=True):text=re.sub(r'\b'+re.escape(name)+r'\b',prefix+name,text)
    return text


def wrapper(w,lanes):
    oracle.validate(w);n=w['n'];width=int(w['q']).bit_length()
    if n%lanes or lanes<1 or lanes&(lanes-1):raise ValueError('invalid preload lane count')
    beats=n//lanes;address=max(1,(beats-1).bit_length());packed=width*lanes
    pieces=[f'''module PreloadedNTT(input clock,reset,start,direction,
input load_valid,input [{address-1}:0] load_address,input [{packed-1}:0] load_data,
input read_valid,input [{address-1}:0] read_address,output reg [{packed-1}:0] read_data,
output reg busy,done,output reg [63:0] elapsed_cycles);
localparam BEATS={beats};
(* ram_style="block" *) reg [{packed-1}:0] operands[0:BEATS-1],results[0:BEATS-1];
reg [{packed-1}:0] word;reg word_valid,selected;reg [63:0] cycles;
integer requested,received;
wire forward_ready,inverse_ready,forward_valid,inverse_valid;
wire [{packed-1}:0] forward_data,inverse_data;
wire input_ready=selected ? inverse_ready : forward_ready;
wire result_valid=selected ? inverse_valid : forward_valid;
wire [{packed-1}:0] result_data=selected ? inverse_data : forward_data;
''']
    for name,inverse in [('Forward',False),('Inverse',True)]:
        direction='selected' if inverse else '!selected'
        ports=','.join(f'.i{j}(word[{j*width} +: {width}]),.o{j}({name.lower()}_data[{j*width} +: {width}])' for j in range(lanes))
        pieces.append(f'{name}SearchTop {name.lower()}( .clock(clock),.reset(reset),.in_valid(busy && word_valid && {direction}),.in_ready({name.lower()}_ready),.out_valid({name.lower()}_valid),.out_ready(busy && {direction}),{ports});')
    pieces.append('''always @(posedge clock)begin
 if(reset)begin busy<=0;done<=0;elapsed_cycles<=0;word_valid<=0;requested<=0;received<=0;selected<=0;cycles<=0;end
 else begin
  done<=0;
  if(!busy && load_valid && load_address<BEATS)operands[load_address]<=load_data;
  if(!busy && read_valid && read_address<BEATS)read_data<=results[read_address];
  if(start && !busy)begin
   busy<=1;selected<=direction;word_valid<=0;requested<=0;received<=0;cycles<=0;
  end else if(busy)begin
   cycles<=cycles+1;
   if(!word_valid || input_ready)begin
    if(requested<BEATS)begin word<=operands[requested];word_valid<=1;requested<=requested+1;end
    else word_valid<=0;
   end
   if(result_valid)begin
    results[received]<=result_data;received<=received+1;
    if(received==BEATS-1)begin busy<=0;word_valid<=0;done<=1;elapsed_cycles<=cycles+1;end
   end
  end
 end
end
endmodule''')
    return '\n'.join(pieces)


def fixtures(w,lanes,vectors):
    oracle.validate(w);n=w['n'];q=int(w['q']);width=q.bit_length()
    if any(len(v)!=n or any(type(x) is not int or not 0<=x<q for x in v) for v in vectors):
        raise ValueError('noncanonical preload corpus')
    def packed(rows):
        return ''.join(f"{sum(x<<(j*width) for j,x in enumerate(row[i:i+lanes])):x}\n"
                       for row in rows for i in range(0,n,lanes))
    expected=[oracle.transform(v,dict(w,direction=direction)) for direction in ('forward','inverse') for v in vectors]
    return {'input.mem':packed(vectors),'expected.mem':packed(expected)}


def testbench(w,lanes,vectors):
    n=w['n'];width=int(w['q']).bit_length();beats=n//lanes;aw=max(1,(beats-1).bit_length());pw=width*lanes
    return f'''module test;
localparam B={beats},F={len(vectors)};
reg clock=0;always #5 clock=~clock;reg reset=1,start=0,direction=0,load_valid=0,read_valid=0;
reg [{aw-1}:0] load_address=0,read_address=0;reg [{pw-1}:0] load_data=0;wire [{pw-1}:0] read_data;
reg [{pw-1}:0] inputs[0:F*B-1],expected[0:2*F*B-1];
wire busy,done;wire [63:0] elapsed_cycles;integer count,pass,trial,beat;
PreloadedNTT dut(clock,reset,start,direction,load_valid,load_address,load_data,read_valid,read_address,read_data,busy,done,elapsed_cycles);
initial begin
$readmemh("input.mem",inputs);$readmemh("expected.mem",expected);
repeat(3)@(negedge clock);reset=0;
for(pass=0;pass<2;pass=pass+1)begin
 for(trial=0;trial<F;trial=trial+1)begin
  for(beat=0;beat<B;beat=beat+1)begin
   @(negedge clock);load_valid=1;load_address=beat;load_data=inputs[trial*B+beat];
  end
  @(negedge clock);load_valid=0;direction=pass==1;start=1;@(negedge clock);start=0;count=0;
  while(!done && count<{n*500})begin @(negedge clock);count=count+1;end
  if(!done || elapsed_cycles!=count)$fatal(1,"preloaded watchdog/counter");
  $display("PRELOADED %s %0d %0d",pass==1?"inverse":"forward",trial,elapsed_cycles);$fflush();
  for(beat=0;beat<B;beat=beat+1)begin
   read_valid=1;read_address=beat;@(posedge clock);#1;
   if(read_data!==expected[(pass*F+trial)*B+beat])$fatal(1,"preloaded pass=%0d trial=%0d beat=%0d",pass,trial,beat);
   @(negedge clock);
  end
  read_valid=0;
  if(trial==0)begin start=1;@(negedge clock);start=0;repeat(5)@(negedge clock);reset=1;repeat(3)@(negedge clock);reset=0;end
 end
end
$display("PASS preloaded transform");$finish;end
endmodule'''
