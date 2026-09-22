"""Counted version-2 composition: field products, CRT, and serial FFT digits."""
import math
from . import wide_products as wide, product_rtl


def ports(w,top='SearchTop'):
    a=wide.input_width(w,'a');b=wide.input_width(w,'b');o=wide.output_width(w)
    return f'module {top}(input clock,reset,in_valid,output in_ready,input [{2*a-1}:0] a,input [{2*b-1}:0] b,output out_valid,input out_ready,output [{2*o-1}:0] out_data);'


def fft_fold(w,scalar,frac):
    n=w['n'];count=wide.output_count(w);ow=wide.output_width(w)
    shift=frac+(2*n).bit_length()-1;integer_width=wide.bound(w).bit_length()+1
    # Identical signed nearest/ties-even function to the separately proved v1 primitive.
    reference=product_rtl.fold_module(n,scalar,frac,integer_width)
    import re
    rounded=re.search(r'function automatic.*?endfunction',reference,re.S).group()
    pieces=[f'''module WideFold(input clock,reset,in_valid,output in_ready,input [{4*scalar-1}:0] in_data,
output out_valid,input out_ready,output [{2*ow-1}:0] out_data);
localparam N={n},W={scalar},OW={integer_width},SHIFT={shift};
reg signed [W-1:0] raw[0:2*N-1];reg full;integer capture,drain,j;
assign in_ready=!full;assign out_valid=full;
{rounded}
''']
    for lane in range(2):
        index=f'(2*drain+{lane})'
        lower=f'$signed({{raw[{index}][W-1],raw[{index}]}})'
        if w['ring']=='linear':expression=lower
        else:
            upper=f'$signed({{raw[{index}+N][W-1],raw[{index}+N]}})'
            expression=lower+(' - ' if w['ring']=='negacyclic' else ' + ')+upper
        pieces.append(f'wire signed [OW-1:0] value{lane}=rounded({expression});')
        if w['modulus']:
            m=w['modulus'];rw=max(integer_width+1,m.bit_length()+1)
            pieces.append(f"wire signed [{rw-1}:0] rem{lane}=$signed(value{lane}) % {rw}'sd{m};")
            result=f"(rem{lane}<0 ? rem{lane}+{rw}'sd{m} : rem{lane})"
        else:result=f'value{lane}'
        pieces.append(f"assign out_data[{lane*ow} +: {ow}]=({index}>={count}) ? {ow}'d0 : {result};")
    pieces.append(f'''always @(posedge clock)begin
if(reset)begin full<=0;capture<=0;drain<=0;end
else begin
 if(in_valid && in_ready)begin
  for(j=0;j<2;j=j+1)raw[2*capture+j]<=in_data[j*2*W +: W];
  if(capture==N-1)begin capture<=0;full<=1;end else capture<=capture+1;
 end
 if(out_valid && out_ready)begin
  if(drain=={(count+1)//2-1})begin drain<=0;full<=0;end else drain<=drain+1;
 end
end
end
endmodule''')
    return '\n'.join(pieces)


def fft_leaf(w,c,forward,inverse):
    scalar=c['integer_bits']+c['fractional_bits'];width=2*scalar;frac=c['fractional_bits']
    pieces=[product_rtl.frame_engine('ForwardFrame','ProductForward',forward,width,w['n']),
            product_rtl.frame_engine('InverseFrame','ProductInverse',inverse,width),
            product_rtl.multiply_module(width,True,frac),fft_fold(w,scalar,frac),ports(w)]
    pieces.append(f'''wire ar,br,av,bv,am,bm,mv,mr,iv,ir;
wire [{2*width-1}:0] a_data,b_data,fa,fb,product,iv_data;
assign in_ready=ar && br;''')
    for op in ('a','b'):
        bits=wide.input_width(w,op);signed=w[op+'_range'][0]<0
        for lane in range(2):
            sign=f'{op}[{lane*bits+bits-1}]' if signed else "1'b0"
            pieces.append(f"wire [{scalar-1}:0] {op}q{lane}={{{{{scalar-bits}{{{sign}}}}},{op}[{lane*bits} +: {bits}]}} << {frac};")
            pieces.append(f"assign {op}_data[{lane*width} +: {width}]={{{scalar}'b0,{op}q{lane}}};")
    pieces.append('''ForwardFrame f_a(clock,reset,in_valid && br,ar,a_data,av,am,fa);
ForwardFrame f_b(clock,reset,in_valid && ar,br,b_data,bv,bm,fb);
ProductMultiply pointwise(clock,reset,av,bv,am,bm,fa,fb,mv,mr,product);
InverseFrame inverse(clock,reset,mv,mr,product,iv,ir,iv_data);
WideFold fold(clock,reset,iv,ir,iv_data,out_valid,out_ready,out_data);
endmodule''')
    return '\n'.join(pieces)


def split_fft(w,leaf):
    n=w['n'];count=wide.output_count(w);ow=wide.output_width(w)
    aw=wide.input_width(w,'a');bw=wide.input_width(w,'b');lw=wide.output_width(leaf)
    accum=wide.bound(w).bit_length()+2;da=(aw+3)//4;db=(bw+3)//4
    pairs=[(i,j) for i in range(da) for j in range(db)
           if not(w['modulus']==1<<32 and i+j>=8)]
    pieces=[ports(w),f'''localparam N={n},COUNT={count},AW={aw},BW={bw},LW={lw},ACC={accum};
reg [AW-1:0] aa[0:N-1];reg [BW-1:0] bb[0:N-1];
reg signed [ACC-1:0] sums[0:{2*((count+1)//2)-1}];
integer state,capture,feed,receive,drain,pair_index,i;integer adigit,bdigit;
reg [9:0] leaf_a,leaf_b;wire leaf_ready,leaf_valid;wire [2*LW-1:0] leaf_data;
assign in_ready=state==0;assign out_valid=state==3;
always @(*)begin
adigit=0;bdigit=0;
case(pair_index)
''']
    pieces.extend(f'{k}:begin adigit={i};bdigit={j};end' for k,(i,j) in enumerate(pairs))
    pieces.append('endcase\nend')
    for op,bits,digits in (('a',aw,da),('b',bw,db)):
        signed=w[op+'_range'][0]<0;last=bits-4*(digits-1)
        pieces.append(f'''function automatic signed [4:0] digit_{op}(input [{bits-1}:0] value,input integer index);
reg [3:0] nibble;
begin nibble=value >> (4*index);
digit_{op}={{1'b0,nibble}};
''')
        if signed:pieces.append(f"if(index=={digits-1})digit_{op}=$signed(value[{bits-1} -: {last}]);")
        pieces.append('end\nendfunction')
    pieces.append('''always @(*)begin
leaf_a={digit_a(aa[2*feed+1],adigit),digit_a(aa[2*feed],adigit)};
leaf_b={digit_b(bb[2*feed+1],bdigit),digit_b(bb[2*feed],bdigit)};
end
DigitProduct leaf(clock,reset,state==1,leaf_ready,leaf_a,leaf_b,leaf_valid,state==2,leaf_data);
''')
    for lane in range(2):
        if w['modulus']:
            rw=max(accum,w['modulus'].bit_length()+1)
            pieces.append(f"wire signed [{rw-1}:0] remainder{lane}=sums[2*drain+{lane}] % {rw}'sd{w['modulus']};")
            result=f"(remainder{lane}<0 ? remainder{lane}+{rw}'sd{w['modulus']} : remainder{lane})"
        else:result=f'sums[2*drain+{lane}]'
        pieces.append(f'assign out_data[{lane*ow} +: {ow}]={result};')
    pieces.append(f'''always @(posedge clock)begin
if(reset)begin state<=0;capture<=0;feed<=0;receive<=0;drain<=0;pair_index<=0;end
else case(state)
0:if(in_valid && in_ready)begin
 aa[2*capture]<=a[AW-1:0];aa[2*capture+1]<=a[2*AW-1:AW];
 bb[2*capture]<=b[BW-1:0];bb[2*capture+1]<=b[2*BW-1:BW];
 if(capture==N/2-1)begin
  capture<=0;feed<=0;pair_index<=0;state<=1;
  for(i=0;i<{2*((count+1)//2)};i=i+1)sums[i]<=0;
 end else capture<=capture+1;
end
1:if(leaf_ready)begin
 if(feed==N/2-1)begin feed<=0;receive<=0;state<=2;end else feed<=feed+1;
end
2:if(leaf_valid)begin
 for(i=0;i<2;i=i+1)
  sums[2*receive+i]<=sums[2*receive+i]+($signed(leaf_data[i*LW +: LW]) <<< (4*(adigit+bdigit)));
 if(receive=={(count+1)//2-1})begin
  receive<=0;
  if(pair_index=={len(pairs)-1})begin state<=3;drain<=0;end
  else begin pair_index<=pair_index+1;state<=1;feed<=0;end
 end else receive<=receive+1;
end
3:if(out_ready)begin
 if(drain=={(count+1)//2-1})begin state<=0;drain<=0;end else drain<=drain+1;
end
endcase
end
endmodule''')
    return '\n'.join(pieces)


def field_product(w,field,forward,inverse,index):
    q=field['q'];d=q.bit_length();prefix=f'Prime{index}';aw=wide.input_width(w,'a');bw=wide.input_width(w,'b')
    pieces=[product_rtl.frame_engine(prefix+'ForwardFrame',prefix+'Forward',forward,d,w['n']),
            product_rtl.frame_engine(prefix+'InverseFrame',prefix+'Inverse',inverse,d),
            f'''module {prefix}Product(input clock,reset,in_valid,output in_ready,
input [{2*aw-1}:0] a,input [{2*bw-1}:0] b,output out_valid,input out_ready,output [{2*d-1}:0] out_data);
wire ar,br,av,bv,am,bm,mr;wire [{2*d-1}:0] a_data,b_data,fa,fb;
reg [1:0] valid;reg [{2*d-1}:0] value;reg [{2*d-1}:0] p0,p1;
wire advance=!valid[1] || mr;
assign am=advance && bv;assign bm=advance && av;assign in_ready=ar && br;
''']
    for op,bits in (('a',aw),('b',bw)):
        cw=max(bits+1,d+2)
        for lane in range(2):
            expression=f'$signed({op}[{lane*bits} +: {bits}])' if w[op+'_range'][0]<0 else f"$signed({{1'b0,{op}[{lane*bits} +: {bits}]}})"
            pieces.append(f"wire signed [{cw-1}:0] lift_{op}{lane}={expression};")
            pieces.append(f"wire signed [{cw-1}:0] rem_{op}{lane}=lift_{op}{lane} % {cw}'sd{q};")
            pieces.append(f"assign {op}_data[{lane*d} +: {d}]=rem_{op}{lane}<0 ? rem_{op}{lane}+{cw}'sd{q}:rem_{op}{lane};")
    pieces.append(f'''{prefix}ForwardFrame f_a(clock,reset,in_valid && br,ar,a_data,av,am,fa);
{prefix}ForwardFrame f_b(clock,reset,in_valid && ar,br,b_data,bv,bm,fb);
{prefix}InverseFrame inverse(clock,reset,valid[1],mr,value,out_valid,out_ready,out_data);
always @(posedge clock)begin
if(reset)valid<=0;
else if(advance)begin
valid<={{valid[0],av && bv}};
p0<=fa[0 +: {d}]*fb[0 +: {d}];p1<=fa[{d} +: {d}]*fb[{d} +: {d}];
value[0 +: {d}]<=p0 % {q};value[{d} +: {d}]<=p1 % {q};
end
end
endmodule''')
    return '\n'.join(pieces)


def rns_product(w,fields):
    q=math.prod(f['q'] for f in fields);qw=q.bit_length();sw=qw+max(f['q'].bit_length() for f in fields)+len(fields).bit_length()+1
    ow=wide.output_width(w);count=wide.output_count(w);pieces=[ports(w)]
    readies=[];valids=[];products=[[],[]]
    for index,field in enumerate(fields):
        p=field['q'];d=p.bit_length();weight=((q//p)*pow(q//p,-1,p))%q
        readies.append(f'ready{index}');valids.append(f'valid{index}')
        pieces.append(f'wire ready{index},valid{index};wire [{2*d-1}:0] data{index};')
        pieces.append(f'Prime{index}Product p{index}(clock,reset,in_valid && in_ready,ready{index},a,b,valid{index},accept,data{index});')
        for lane in range(2):
            term=f'p{index}_{lane}';products[lane].append(term)
            pieces.append(f'reg [{sw-1}:0] {term};')
    pieces.append(f'''reg [2:0] valid;wire advance=!valid[2] || out_ready;
wire all_valid={' && '.join(valids)};
wire accept=advance && all_valid;
assign in_ready={' && '.join(readies)};assign out_valid=valid[2];
reg [{qw-1}:0] residues0,residues1;
reg [{ow-1}:0] result0,result1;
assign out_data={{result1,result0}};
''')
    for lane in range(2):
        pieces.append(f"wire signed [{qw}:0] centered{lane}=residues{lane}>{qw}'d{q//2} ? $signed({{1'b0,residues{lane}}})-{qw+1}'sd{q} : $signed({{1'b0,residues{lane}}});")
        if w['modulus']:
            rw=max(qw+1,w['modulus'].bit_length()+1)
            pieces.append(f"wire signed [{rw-1}:0] reduced{lane}=centered{lane} % {rw}'sd{w['modulus']};")
    pieces.append('always @(posedge clock)begin\nif(reset)valid<=0;\nelse if(advance)begin\nvalid<={valid[1:0],all_valid};')
    for index,field in enumerate(fields):
        p=field['q'];d=p.bit_length();weight=((q//p)*pow(q//p,-1,p))%q
        for lane in range(2):pieces.append(f"p{index}_{lane}<=data{index}[{lane*d} +: {d}]*{sw}'d{weight};")
    for lane in range(2):
        pieces.append(f"residues{lane}<=({' + '.join(products[lane])}) % {sw}'d{q};")
        if w['modulus']:
            rw=max(qw+1,w['modulus'].bit_length()+1)
            pieces.append(f"result{lane}<=reduced{lane}<0 ? reduced{lane}+{rw}'sd{w['modulus']} : reduced{lane};")
        else:pieces.append(f'result{lane}<=centered{lane};')
    pieces.append('end\nend\nendmodule')
    return '\n'.join(pieces)
