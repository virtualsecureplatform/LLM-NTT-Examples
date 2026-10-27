import json
import csv
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from architecture_search import frame_banks,modular_pipeline,pipelined_products,wide_products as wide
from scripts import polynomial_study as study


def rtl_check(rtl,inputs,expected,iw,ow):
    """Independent scoreboard with random gaps, backpressure, and in-flight reset."""
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        (root/'design.sv').write_text(rtl)
        (root/'inputs.mem').write_text(''.join(f'{x:x}\n' for x in inputs))
        (root/'expected.mem').write_text(''.join(f'{x:x}\n' for x in expected))
        (root/'test.sv').write_text(f'''module test;
reg clock=0,reset=1,in_valid=0,out_ready=0;wire in_ready,out_valid;
reg [{iw-1}:0] in_data;wire [{ow-1}:0] out_data;
reg [{iw-1}:0] inputs[0:{len(inputs)-1}];reg [{ow-1}:0] expected[0:{len(expected)-1}];
integer sent,received,cycle,pass,i;reg stalled,source_stalled;reg [{ow-1}:0] held;
UUT dut(clock,reset,in_valid,in_ready,in_data,out_valid,out_ready,out_data);
always #5 clock=~clock;
initial begin
$readmemh("inputs.mem",inputs);$readmemh("expected.mem",expected);
for(pass=0;pass<3;pass=pass+1)begin
reset=1;in_valid=0;out_ready=0;repeat(3)@(negedge clock);reset=0;
// Cancel partially captured input and partially executed arithmetic.
in_valid=1;in_data=inputs[0];repeat(pass==0?3:150)@(negedge clock);
reset=1;in_valid=0;repeat(3)@(negedge clock);reset=0;
sent=0;received=0;stalled=0;source_stalled=0;
for(cycle=0;cycle<200000 && received<{len(expected)};cycle=cycle+1)begin
in_valid=sent<{len(inputs)} && (source_stalled || pass==0 || cycle%11!=4);
out_ready=pass==0 || cycle%7!=3;
if(sent<{len(inputs)})in_data=inputs[sent];
@(posedge clock);
if(stalled && (!out_valid || out_data!==held))$fatal(1,"unstable stalled output");
held=out_data;stalled=out_valid && !out_ready;source_stalled=in_valid && !in_ready;
if(in_valid && in_ready)sent=sent+1;
if(out_valid && out_ready)begin
if(received>={len(expected)} || out_data!==expected[received])$fatal(1,"mismatch beat=%0d got=%h expected=%h",received,out_data,expected[received]);
received=received+1;
end
@(negedge clock);
end
if(sent!={len(inputs)} || received!={len(expected)})$fatal(1,"watchdog sent=%0d received=%0d",sent,received);
in_valid=0;out_ready=1;repeat(200)begin @(posedge clock);if(out_valid)$fatal(1,"extra output");@(negedge clock);end
end
$display("PASS");$finish;
end
endmodule''')
        build=subprocess.run(['iverilog','-g2012','-s','test','-o','sim','design.sv','test.sv'],cwd=root,
                             capture_output=True,text=True,timeout=60)
        if build.returncode:raise AssertionError(build.stdout+build.stderr)
        result=subprocess.run(['vvp','sim'],cwd=root,capture_output=True,text=True,timeout=60)
        if result.returncode or 'PASS' not in result.stdout:
            raise AssertionError(result.stdout+result.stderr)


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'run in the pinned simulation container')
class PipelinedRTLTests(unittest.TestCase):
    def test_unsigned_and_signed_moduli_including_crt_widths(self):
        rng=random.Random(912)
        for q,width,signed in [(17,10,False),(65537,34,True),(2013265921,62,False),
                               (469762049*1811939329*2013265921,126,True)]:
            with self.subTest(q=q,width=width,signed=signed):
                values=[0,1,q-1,q,q+1,(1<<(width-1))-1,1<<(width-1),(1<<width)-1]
                values += [rng.getrandbits(width) for _ in range(120)]
                if width==10:values=list(range(1<<width))
                words=[];gold=[];d=q.bit_length()
                for x,y in zip(values,values[::-1]):
                    def residue(v):
                        if signed and v>>(width-1):v-=1<<width
                        return v%q
                    words.append(x | y<<width);gold.append(residue(x) | residue(y)<<d)
                rtl_check(modular_pipeline.emit('UUT',width,q,2,signed),words,gold,2*width,2*d)

    def test_banked_lane_conversion_padding_gaps_and_resets(self):
        rng=random.Random(41)
        for k,e,n,input_n,registered in [(*c,r) for c in [(2,2,16,16),(4,2,16,8),(2,4,16,16),(8,2,16,8)] for r in (False,True)]:
            with self.subTest(k=k,e=e,input_n=input_n,registered=registered):
                meta=dict(transform_size=n,streaming_width=k,protocol='ready-valid',latency=1,
                          initiation_interval=n//k)
                core=f'''module Core(input clock,reset,in_valid,output in_ready,output reg out_valid,input out_ready,
{','.join(f'input [15:0] i{i},output reg [15:0] o{i}' for i in range(k))});
assign in_ready=!out_valid || out_ready;
always @(posedge clock)if(reset)out_valid<=0;else if(in_ready)begin out_valid<=in_valid;
{''.join(f'o{i}<=i{i};' for i in range(k))}end
endmodule'''
                inputs=[];expected=[]
                for frame in range(20):
                    values=[rng.randrange(65536) for _ in range(input_n)]
                    inputs += [sum(x<<(16*j) for j,x in enumerate(values[i:i+e])) for i in range(0,input_n,e)]
                    values += [0]*(n-input_n)
                    expected += [sum(x<<(16*j) for j,x in enumerate(values[i:i+e])) for i in range(0,n,e)]
                rtl_check(core+'\n'+frame_banks.emit('UUT','Core',meta,16,input_n,e,registered_output=registered),inputs,expected,e*16,e*16)

    def test_native_input_register_frame_feed_honors_midframe_stalls(self):
        for k in (4,16):
            meta=dict(transform_size=16,streaming_width=k,protocol='ready-valid',latency=2,
                      initiation_interval=16//k,architecture_parameters=dict(input_register=1))
            core=f"""module Core(input clock,reset,in_valid,output in_ready,output reg out_valid,input out_ready,
{','.join(f'input [15:0] i{i},output reg [15:0] o{i}' for i in range(k))});
reg [3:0] phase;wire advance=!out_valid || out_ready;wire permit=phase<3;
assign in_ready=advance && permit;
always @(posedge clock)begin
if(reset)begin out_valid<=0;phase<=0;end else begin
phase<=phase==6?0:phase+1;
if(advance)begin out_valid<=in_valid && permit;if(in_valid && permit)begin
{''.join(f'o{i}<=i{i};' for i in range(k))}end end end end
endmodule"""
            values=list(range(16*20))
            words=[values[i] | (values[i+1]<<16) for i in range(0,len(values),2)]
            rtl_check(core+'\n'+frame_banks.emit('UUT','Core',meta,16,external_lanes=2),words,words,32,32)

    def test_field_products_with_identity_transform_stubs(self):
        rng=random.Random(17)
        w=wide.workload(8,2147483647,'negacyclic',1<<32)
        meta=dict(transform_size=8,streaming_width=2,protocol='ready-valid',latency=1,initiation_interval=4)
        for q,profile in [(q,p) for q in (65537,2013265921) for p in ('pipelined','registered')]:
            d=q.bit_length();field=wide.roots(q,8,True)
            cores=[]
            for direction in ('Forward','Inverse'):
                cores.append(f'''module Prime0{direction}(input clock,reset,in_valid,output in_ready,output reg out_valid,input out_ready,
input [{d-1}:0] i0,i1,output reg [{d-1}:0] o0,o1);
assign in_ready=!out_valid || out_ready;
always @(posedge clock)if(reset)out_valid<=0;else if(in_ready)begin out_valid<=in_valid;o0<=i0;o1<=i1;end
endmodule''')
            inputs=[];expected=[]
            for beat in range(80):
                a=[rng.randint(-2147483648,2147483647) for _ in range(2)]
                b=[rng.randint(-2147483648,2147483647) for _ in range(2)]
                inputs.append(sum((v&0xffffffff)<<(32*i) for i,v in enumerate(a+b)))
                expected.append(sum((x*y%q)<<(d*i) for i,(x,y) in enumerate(zip(a,b))))
            wrapper=f'''module UUT(input clock,reset,in_valid,output in_ready,input [127:0] in_data,
output out_valid,input out_ready,output [{2*d-1}:0] out_data);
Prime0Product product(clock,reset,in_valid,in_ready,in_data[63:0],in_data[127:64],out_valid,out_ready,out_data);
endmodule'''
            rtl_check('\n'.join(cores)+'\n'+pipelined_products.field_product(w,field,meta,meta,0,profile)+'\n'+wrapper,
                      inputs,expected,128,2*d)

    def test_crt_reconstruction_with_unequal_prime_delays(self):
        rng=random.Random(77)
        for modulus in (None,17,1000000007,1<<32):
            with self.subTest(modulus=modulus):
                w=wide.workload(16,2147483647,'negacyclic',modulus);fields=wide.basis(w)
                ow=wide.output_width(w);cores=[]
                for index,field in enumerate(fields):
                    q=field['q'];d=q.bit_length();stages=index+1
                    cores.append(f'''module Prime{index}Product(input clock,reset,in_valid,output in_ready,
input [63:0] a,b,output out_valid,input out_ready,output [{2*d-1}:0] out_data);
reg [{stages-1}:0] valid;reg [{2*d-1}:0] data[0:{stages-1}];integer i;
wire advance=!valid[{stages-1}] || out_ready;
assign in_ready=advance;assign out_valid=valid[{stages-1}];assign out_data=data[{stages-1}];
wire signed [63:0] p0=$signed(a[31:0])*$signed(b[31:0]);
wire signed [63:0] p1=$signed(a[63:32])*$signed(b[63:32]);
function automatic [{d-1}:0] residue(input signed [63:0] x);
reg signed [64:0] r;begin r=x % 65'sd{q};residue=r<0?r+65'sd{q}:r;end endfunction
always @(posedge clock)begin
if(reset)valid<=0;else if(advance)begin
valid[0]<=in_valid;data[0]<={{residue(p1),residue(p0)}};
for(i=1;i<{stages};i=i+1)begin valid[i]<=valid[i-1];data[i]<=data[i-1];end
end end endmodule''')
                words=[];gold=[]
                for i in range(128):
                    a=[rng.randint(-2147483648,2147483647) for _ in range(2)]
                    b=[rng.randint(-2147483648,2147483647) for _ in range(2)]
                    if i==0:a=[-2147483648,2147483647];b=[-2147483648,-2147483648]
                    words.append(sum((v&0xffffffff)<<(32*j) for j,v in enumerate(a+b)))
                    gold.append(sum(((x*y%modulus if modulus else x*y)&((1<<ow)-1))<<(ow*j)
                                    for j,(x,y) in enumerate(zip(a,b))))
                wrapper=f'''module UUT(input clock,reset,in_valid,output in_ready,input [127:0] in_data,
output out_valid,input out_ready,output [{2*ow-1}:0] out_data);
SearchTop product(clock,reset,in_valid,in_ready,in_data[63:0],in_data[127:64],out_valid,out_ready,out_data);
endmodule'''
                rtl_check('\n'.join(cores)+'\n'+pipelined_products.rns_product(w,fields)+'\n'+wrapper,
                          words,gold,128,2*ow)

    def test_serial_fft_accumulation_banks_and_modulus(self):
        rng=random.Random(89)
        cases=[('negacyclic',1<<32,(-2147483648,2147483647),i) for i in (0,1,2)]
        cases += [('negacyclic',1<<32,b,1) for b in ((-128,127),(-1,1))]
        cases += [(ring,m,(-2147483648,2147483647),0) for ring,m in
                  [('cyclic',1<<32),('linear',1<<32),('negacyclic',1000000007),('negacyclic',None)]]
        for ring,modulus,b_range,omitted in cases:
            with self.subTest(ring=ring,modulus=modulus,b_range=b_range,omitted=omitted):
                w={**wide.workload(8,2147483647,ring,modulus),'a_range':[-2147483648,2147483647],
                   'b_range':list(b_range)}
                leaf=wide.workload(8,15,ring);lw=wide.output_width(leaf);count=wide.output_count(w)
                ob=(count+1)//2;ow=wide.output_width(w);aw=wide.input_width(w,'a');bw=wide.input_width(w,'b')
                accumulate=(f'results[(i+j)%8]=results[(i+j)%8]'+
                            ('-left[i]*right[j];' if ring=='negacyclic' else '+left[i]*right[j];'))
                if ring=='negacyclic':accumulate='if(i+j>=8)'+accumulate+'else results[i+j]=results[i+j]+left[i]*right[j];'
                if ring=='linear':accumulate='results[i+j]=results[i+j]+left[i]*right[j];'
                stub=f'''module DigitProduct(input clock,reset,in_valid,output in_ready,input [9:0] a,b,
output out_valid,input out_ready,output [{2*lw-1}:0] out_data);
reg [1:0] state;integer beat,i,j;
reg signed [4:0] left[0:7],right[0:7];reg signed [63:0] results[0:{2*ob-1}];
assign in_ready=state==0;assign out_valid=state==2;
assign out_data={{results[2*beat+1][{lw-1}:0],results[2*beat][{lw-1}:0]}};
always @(posedge clock)begin
if(reset)begin state<=0;beat<=0;end
else case(state)
0:if(in_valid)begin
left[2*beat]<=a[4:0];left[2*beat+1]<=a[9:5];right[2*beat]<=b[4:0];right[2*beat+1]<=b[9:5];
if(beat==3)begin beat<=0;state<=1;end else beat<=beat+1;
end
1:begin
for(i=0;i<{2*ob};i=i+1)results[i]=0;
for(i=0;i<8;i=i+1)for(j=0;j<8;j=j+1)begin {accumulate} end
state<=2;
end
2:if(out_ready)begin if(beat=={ob-1})begin beat<=0;state<=0;end else beat<=beat+1;end
endcase
end endmodule'''
                words=[];gold=[]
                for frame in range(4):
                    a=[rng.randint(*w['a_range']) for _ in range(8)];b=[rng.randint(*w['b_range']) for _ in range(8)]
                    if frame==0:a=[w['a_range'][0]]*8;b=[w['b_range'][0]]*8
                    for i in range(0,8,2):
                        words.append(sum((x&((1<<aw)-1))<<(aw*j) for j,x in enumerate(a[i:i+2])) |
                                     sum((x&((1<<bw)-1))<<(2*aw+bw*j) for j,x in enumerate(b[i:i+2])))
                    out=wide.omitted_product(w,a,b,omitted) if omitted else wide.schoolbook(w,a,b)
                    out += [0]*(2*ob-len(out))
                    gold += [sum((x&((1<<ow)-1))<<(ow*j) for j,x in enumerate(out[i:i+2])) for i in range(0,2*ob,2)]
                wrapper=f'''module UUT(input clock,reset,in_valid,output in_ready,input [{2*(aw+bw)-1}:0] in_data,
output out_valid,input out_ready,output [{2*ow-1}:0] out_data);
SearchTop product(clock,reset,in_valid,in_ready,in_data[{2*aw-1}:0],in_data[{2*(aw+bw)-1}:{2*aw}],out_valid,out_ready,out_data);
endmodule'''
                rtl_check(stub+'\n'+pipelined_products.split_fft(w,leaf,omitted)+'\n'+wrapper,
                          words,gold,2*(aw+bw),2*ow)


class ProductProfileTests(unittest.TestCase):
    def test_baseline_ids_unchanged_and_profiles_have_distinct_ids(self):
        root=Path(__file__).resolve().parents[2]
        spec=json.loads((root/'studies/torus-demo.json').read_text())
        old=study.enumerate_points(spec)
        with (root/'docs/results/torus32-points.csv').open() as stream:
            self.assertEqual({r['name'] for r in old},{r['name'] for r in csv.DictReader(stream)})
        spec['product_profile']='pipelined';new=study.enumerate_points(spec)
        self.assertEqual(len(old),len(new))
        self.assertFalse({r['name'] for r in old}&{r['name'] for r in new})
        self.assertTrue(all(r['configuration']['product_profile']=='pipelined' for r in new if 'configuration' in r))
        w=wide.workload(16,2147483647,'negacyclic',1<<32)
        rows=wide.candidates(w,dict(generators=['ngen'],product_profiles=['baseline','pipelined']))
        self.assertEqual(len(rows),2)
        self.assertNotIn('product_profile',rows[0]);self.assertEqual(rows[1]['product_profile'],'pipelined')


if __name__=='__main__':unittest.main()
