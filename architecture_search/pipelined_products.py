"""Timing-oriented, elastic product adapters; baseline RTL remains unchanged."""
import math
from . import wide_products as wide,product_rtl,modular_pipeline


def field_product(w,field,forward,inverse,index,product_profile='pipelined'):
    q=field['q'];d=q.bit_length();prefix=f'Prime{index}';aw=wide.input_width(w,'a');bw=wide.input_width(w,'b')
    cw=max(aw+1,bw+1,d+2)
    pieces=[product_rtl.frame_engine(prefix+'ForwardFrame',prefix+'Forward',forward,d,w['n'],product_profile=product_profile),
            product_rtl.frame_engine(prefix+'InverseFrame',prefix+'Inverse',inverse,d,product_profile=product_profile),
            modular_pipeline.emit(prefix+'Lift',cw,q,4,True),
            modular_pipeline.emit(prefix+'Pointwise',2*d,q,2),
            f'''module {prefix}Product(input clock,reset,in_valid,output in_ready,
input [{2*aw-1}:0] a,input [{2*bw-1}:0] b,output out_valid,input out_ready,output [{2*d-1}:0] out_data);
wire ar,br,av,bv,am,bm,mr,lr,lv,pv,pr;wire [{4*cw-1}:0] lifted;
wire [{4*d-1}:0] residues;wire [{2*d-1}:0] fa,fb,products;
reg product_valid;reg [{2*d-1}:0] p0,p1;
wire advance=!product_valid || pr;
assign am=advance && bv;assign bm=advance && av;
''']
    for i,(op,bits,lane) in enumerate((op,bits,lane) for op,bits in (('a',aw),('b',bw)) for lane in range(2)):
        value=f'{op}[{lane*bits} +: {bits}]'
        if w[op+'_range'][0]<0:value=f'$signed({value})'
        else:value=f"$signed({{1'b0,{value}}})"
        pieces.append(f'wire signed [{cw-1}:0] lift{i}={value};assign lifted[{i*cw} +: {cw}]=lift{i};')
    pieces.append(f'''{prefix}Lift lift(clock,reset,in_valid,in_ready,lifted,lv,ar && br,residues);
{prefix}ForwardFrame f_a(clock,reset,lv && br,ar,residues[0 +: {2*d}],av,am,fa);
{prefix}ForwardFrame f_b(clock,reset,lv && ar,br,residues[{2*d} +: {2*d}],bv,bm,fb);
{prefix}Pointwise pointwise(clock,reset,product_valid,pr,{{p1,p0}},pv,mr,products);
{prefix}InverseFrame inverse(clock,reset,pv,mr,products,out_valid,out_ready,out_data);
always @(posedge clock)begin
if(reset)product_valid<=0;
else if(advance)begin
product_valid<=av && bv;
p0<=fa[0 +: {d}]*fb[0 +: {d}];p1<=fa[{d} +: {d}]*fb[{d} +: {d}];
end
end
endmodule''')
    return '\n'.join(pieces)


def rns_product(w,fields):
    from .wide_rtl import ports
    q=math.prod(f['q'] for f in fields);qw=q.bit_length()
    sw=qw+max(f['q'].bit_length() for f in fields)+len(fields).bit_length()+1
    ow=wide.output_width(w);modulus=w['modulus'];direct=modulus is None or not modulus&(modulus-1)
    pieces=[modular_pipeline.emit('CRTModulo',sw,q,2)]
    rw=max(qw+1,modulus.bit_length()) if not direct else qw+1
    if not direct:pieces.append(modular_pipeline.emit('CRTOutputModulo',rw,modulus,2,True))
    pieces.append(ports(w))
    readies=[];valids=[];terms=[[],[]]
    for i,field in enumerate(fields):
        d=field['q'].bit_length();readies.append(f'ready{i}');valids.append(f'valid{i}')
        pieces.append(f'''wire ready{i},valid{i};wire [{2*d-1}:0] data{i};
Prime{i}Product p{i}(clock,reset,in_valid && in_ready,ready{i},a,b,valid{i},accept,data{i});''')
        for lane in range(2):
            term=f'p{i}_{lane}';terms[lane].append(term);pieces.append(f'reg [{sw-1}:0] {term};')
    pieces.append(f'''reg [1:0] valid;wire reduce_ready,reduce_valid,reduce_accept;
wire [{2*qw-1}:0] residues;reg [{sw-1}:0] sum0,sum1;
wire advance=!valid[1] || reduce_ready;
wire all_valid={' && '.join(valids)};wire accept=advance && all_valid;
assign in_ready={' && '.join(readies)};
CRTModulo reduce(clock,reset,valid[1],reduce_ready,{{sum1,sum0}},reduce_valid,reduce_accept,residues);
''')
    for lane in range(2):
        pieces.append(f'''wire signed [{qw}:0] centered{lane}=residues[{lane*qw} +: {qw}]>{qw}'d{q//2}
? $signed({{1'b0,residues[{lane*qw} +: {qw}]}})-{qw+1}'sd{q}
: $signed({{1'b0,residues[{lane*qw} +: {qw}]}});''')
    if direct:
        pieces.append(f'''reg output_valid;reg [{ow-1}:0] result0,result1;
assign reduce_accept=!output_valid || out_ready;assign out_valid=output_valid;assign out_data={{result1,result0}};
always @(posedge clock)begin
if(reset)output_valid<=0;
else if(reduce_accept)begin output_valid<=reduce_valid;result0<=centered0;result1<=centered1;end
end''')
    else:
        md=modulus.bit_length()
        pieces.append(f'''wire [{2*md-1}:0] reduced;
wire signed [{rw-1}:0] extend0=centered0,extend1=centered1;
CRTOutputModulo output_reduce(clock,reset,reduce_valid,reduce_accept,{{extend1,extend0}},out_valid,out_ready,reduced);
assign out_data={{reduced[{md} +: {ow}],reduced[0 +: {ow}]}};''')
    pieces.append('always @(posedge clock)begin\nif(reset)valid<=0;\nelse if(advance)begin\nvalid<={valid[0],all_valid};')
    for i,field in enumerate(fields):
        p=field['q'];d=p.bit_length();weight=(q//p)*pow(q//p,-1,p)%q
        for lane in range(2):pieces.append(f"p{i}_{lane}<=data{i}[{lane*d} +: {d}]*{sw}'d{weight};")
    for lane in range(2):pieces.append(f"sum{lane}<={' + '.join(terms[lane])};")
    pieces.append('end\nend\nendmodule')
    return '\n'.join(pieces)


def split_fft(w,leaf,omit_low_diagonals):
    from .wide_rtl import ports
    n=w['n'];count=wide.output_count(w);aw=wide.input_width(w,'a');bw=wide.input_width(w,'b')
    ow=wide.output_width(w);lw=wide.output_width(leaf);acc=wide.bound(w).bit_length()+2
    da=(aw+3)//4;db=(bw+3)//4
    omitted=set(wide.omitted_digit_pairs(w,omit_low_diagonals)) if omit_low_diagonals else set()
    pairs=[(i,j) for i in range(da) for j in range(db) if (i,j) not in omitted
           and not(w['modulus']==1<<32 and i+j>=8)]
    if not pairs:raise ValueError('at least one digit product required')
    beats=(count+1)//2;addr=max(1,(beats-1).bit_length());capbits=max(1,(n//2-1).bit_length())
    m=w['modulus'];direct=m is None or not m&(m-1)
    pieces=[]
    if not direct:pieces.append(modular_pipeline.emit('FFTOutputModulo',max(acc,m.bit_length()),m,2,True))
    pieces.extend([ports(w),f'''localparam N={n},LW={lw},ACC={acc};
reg [{aw-1}:0] aa_even[0:N/2-1],aa_odd[0:N/2-1];
reg [{bw-1}:0] bb_even[0:N/2-1],bb_odd[0:N/2-1];
reg signed [ACC-1:0] sums_even[0:{beats-1}],sums_odd[0:{beats-1}];
reg signed [ACC-1:0] sum_read_even,sum_read_odd,add_even,add_odd;
reg [{addr-1}:0] pending_address;
reg pending,pending_first;reg [2:0] state;
reg [{capbits-1}:0] capture,feed;reg [{addr-1}:0] receive,drain;
reg [{max(1,(len(pairs)-1).bit_length())-1}:0] pair_index;
integer adigit,bdigit;
wire [9:0] leaf_a,leaf_b;wire leaf_ready,leaf_valid;wire [2*LW-1:0] leaf_data;
wire drain_ready;wire leaf_accept=state==2 && leaf_valid;
wire prefetch=state==4 && !pending && pair_index=={len(pairs)-1};
wire drain_next=state==3 && drain_ready && drain!={beats-1};
wire [{addr-1}:0] read_address=prefetch ? 0 : (state==3 ? drain+1'b1 : receive);
assign in_ready=state==0;
always @(*)begin adigit=0;bdigit=0;case(pair_index)
'''])
    pieces.extend(f'{i}:begin adigit={a};bdigit={b};end' for i,(a,b) in enumerate(pairs))
    pieces.append('endcase\nend')
    for op,bits,digits in (('a',aw,da),('b',bw,db)):
        last=bits-4*(digits-1)
        pieces.append(f'''function automatic signed [4:0] digit_{op}(input [{bits-1}:0] value,input integer index);
reg [3:0] nibble;begin nibble=value >> (4*index);digit_{op}={{1'b0,nibble}};''')
        if w[op+'_range'][0]<0:pieces.append(f"if(index=={digits-1})digit_{op}=$signed(value[{bits-1} -: {last}]);")
        pieces.append('end\nendfunction')
    pieces.append('''assign leaf_a={digit_a(aa_odd[feed],adigit),digit_a(aa_even[feed],adigit)};
assign leaf_b={digit_b(bb_odd[feed],bdigit),digit_b(bb_even[feed],bdigit)};
DigitProduct leaf(clock,reset,state==1,leaf_ready,leaf_a,leaf_b,leaf_valid,state==2,leaf_data);''')
    if direct:
        pieces.append(f'''assign out_valid=state==3;assign drain_ready=out_ready;
assign out_data[0 +: {ow}]=$signed(sum_read_even);
assign out_data[{ow} +: {ow}]=$signed(sum_read_odd);''')
    else:
        rw=max(acc,m.bit_length());md=m.bit_length()
        pieces.append(f'''wire signed [{rw-1}:0] rem_even=sum_read_even,rem_odd=sum_read_odd;
wire [{2*md-1}:0] reduced;
FFTOutputModulo reduce(clock,reset,state==3,drain_ready,{{rem_odd,rem_even}},out_valid,out_ready,reduced);
assign out_data={{reduced[{md} +: {ow}],reduced[0 +: {ow}]}};''')
    pieces.append(f'''// Exactly one synchronous read and one write per accumulation bank.
always @(posedge clock)begin
if(leaf_accept || prefetch || drain_next)begin
sum_read_even<=sums_even[read_address];sum_read_odd<=sums_odd[read_address];
end
if(pending && !reset)begin
sums_even[pending_address]<=(pending_first ? {{ACC{{1'b0}}}} : sum_read_even)+add_even;
sums_odd[pending_address]<=(pending_first ? {{ACC{{1'b0}}}} : sum_read_odd)+add_odd;
end
if(leaf_accept)begin
add_even<=$signed(leaf_data[0 +: LW]) <<< (4*(adigit+bdigit));
add_odd<=$signed(leaf_data[LW +: LW]) <<< (4*(adigit+bdigit));
pending_address<=receive;pending_first<=pair_index==0;
end
end
always @(posedge clock)begin
if(reset)begin state<=0;capture<=0;feed<=0;receive<=0;drain<=0;pair_index<=0;pending<=0;end
else begin
pending<=leaf_accept;
case(state)
0:if(in_valid && in_ready)begin
aa_even[capture]<=a[0 +: {aw}];aa_odd[capture]<=a[{aw} +: {aw}];
bb_even[capture]<=b[0 +: {bw}];bb_odd[capture]<=b[{bw} +: {bw}];
if(capture==N/2-1)begin capture<=0;feed<=0;pair_index<=0;state<=1;end else capture<=capture+1;
end
1:if(leaf_ready)begin
if(feed==N/2-1)begin feed<=0;receive<=0;state<=2;end else feed<=feed+1;
end
2:if(leaf_accept)begin
if(receive=={beats-1})begin receive<=0;state<=4;end else receive<=receive+1;
end
4:if(!pending)begin
if(pair_index=={len(pairs)-1})begin state<=3;drain<=0;end
else begin pair_index<=pair_index+1;feed<=0;state<=1;end
end
3:if(drain_ready)begin
if(drain=={beats-1})begin state<=0;drain<=0;end else drain<=drain+1;
end
endcase
end
end
endmodule''')
    return '\n'.join(pieces)
