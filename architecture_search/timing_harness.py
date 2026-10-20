"""Registered on-chip stimulus and sink for routed product-kernel timing."""
from . import wide_products as wide
from pathlib import Path
from .model import run,write_json,artifact_manifest,file_hash

LEGACY_CONTEXT = 'registered-harness-v1'
CONTEXT = 'registered-harness-v2'
CONTEXTS = (LEGACY_CONTEXT,CONTEXT)


def vectors(w,frames=3):
    astate=0x123456789abcdef1;bstate=0x6b72d901;inputs=[];outputs=[]
    for frame in range(frames):
        a=[];b=[]
        for beat in range(w['n']//2):
            av=[(astate>>(32*j))&0xffffffff for j in range(2)]
            bv=[{0:0,1:1,2:-1,3:0}[(bstate>>(2*j))&3] for j in range(2)]
            inputs.append(astate | sum((x&3)<<(2*j) for j,x in enumerate(bv))<<64)
            a.extend(x if x<1<<31 else x-(1<<32) for x in av);b.extend(bv)
            astate=((astate<<1)|((astate>>63 ^ astate>>62 ^ astate>>60 ^ astate>>59)&1))&((1<<64)-1)
            bstate=((bstate<<1)|((bstate>>31 ^ bstate>>21 ^ bstate>>1 ^ bstate)&1))&0xffffffff
        gold=wide.schoolbook(w,a,b)
        outputs.extend((gold[i]&0xffffffff)|((gold[i+1]&0xffffffff)<<32) for i in range(0,len(gold),2))
    return inputs,outputs


def validate(row,rtl,directory,context=CONTEXT):
    """Execute the real kernel and harness against independent integer products."""
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    rtl=Path(rtl).resolve();inputs,outputs=vectors(row['workload'])
    harness=directory/'TimingHarness.sv';harness.write_text(emit(row['workload'],context))
    for name,values in [('inputs',inputs),('expected',outputs)]:
        (directory/(name+'.mem')).write_text(''.join(f'{v:x}\n' for v in values))
    tb=directory/'test.sv'
    tb.write_text(f'''module BUFG(input I,output O);assign O=I;endmodule
module test;
reg clock=0;wire [63:0] signature;TimingHarness dut(clock,signature);
always #2 clock=~clock;
reg [67:0] inputs[0:{len(inputs)-1}];reg [63:0] expected[0:{len(outputs)-1}];
reg [63:0] accumulated=0,held;reg stalled=0;integer sent=0,received=0,cycles;
initial begin
$readmemh("inputs.mem",inputs);$readmemh("expected.mem",expected);
for(cycles=0;cycles<200000;cycles=cycles+1)begin
@(posedge clock);
if(!dut.reset)begin
if(dut.source_valid && dut.in_ready)begin
if(sent<{len(inputs)} && {{dut.b1,dut.b0,dut.source_a}}!==inputs[sent])$fatal(1,"source mismatch %0d",sent);
sent=sent+1;
end
if(stalled && (!dut.out_valid || dut.result!==held))$fatal(1,"unstable stalled output");
held=dut.result;stalled=dut.out_valid && !dut.sink_ready;
if(dut.out_valid && dut.sink_ready)begin
if(dut.result!==expected[received])$fatal(1,"result mismatch beat %0d got %h expected %h",received,dut.result,expected[received]);
accumulated={{accumulated[62:0],accumulated[63]}}^expected[received];received=received+1;
end
end
@(negedge clock);
if(signature!==accumulated)$fatal(1,"signature mismatch");
if(received=={len(outputs)})begin $display("PASS harness: %0d output beats",received);$finish;end
end
$fatal(1,"harness watchdog received %0d",received);
end
endmodule
''')
    if context==CONTEXT:tb.write_text(tb.read_text().replace('TimingHarness dut(clock,signature);','TimingHarness dut(clock);assign signature=dut.signature;'))
    inputs_manifest=artifact_manifest([rtl,harness,tb,directory/'inputs.mem',directory/'expected.mem'])
    build=run(['iverilog','-g2012','-s','test','-o','sim',str(rtl),str(harness),str(tb)],directory,directory/'compile.log',180)
    simulation=run(['vvp','sim'],directory,directory/'simulation.log',600) if build['returncode']==0 else None
    passed=bool(simulation and simulation['returncode']==0 and 'PASS harness' in (directory/'simulation.log').read_text())
    e=dict(passed=passed,rtl_sha256=file_hash(rtl),harness_sha256=file_hash(harness),frames=3,
           oracle='independent-python-integer-schoolbook',build=build,simulation=simulation,
           inputs_unchanged=inputs_manifest==artifact_manifest(inputs_manifest['files']))
    e['passed']=e['passed'] and e['inputs_unchanged']
    e['integrity']=dict(version=1,inputs_unchanged=e['inputs_unchanged'],inputs=inputs_manifest,
        outputs=artifact_manifest([p for p in directory.glob('*.log')]),
        measurement={k:e[k] for k in ('passed','rtl_sha256','harness_sha256','frames','oracle')})
    write_json(directory/'validation.json',e)
    if not passed:raise ValueError('harness functional validation failed: '+str(directory))
    return e


def emit(workload,context=CONTEXT):
    aw=wide.input_width(workload,'a');bw=wide.input_width(workload,'b')
    ow=wide.output_width(workload)
    if ((aw,bw,ow)!=(32,2,32) or workload['b_range']!=[-1,1] or
        workload['a_range']!=[-2147483648,2147483647] or workload['modulus']!=1<<32):
        raise ValueError('timing harness v1 requires signed full32 x ternary, output32')
    if context not in CONTEXTS:raise ValueError('unknown harness context')
    text='''module TimingHarness(input clock,output [63:0] signature);
wire kernel_clock;
BUFG clock_buffer(.I(clock),.O(kernel_clock));
reg [3:0] startup=4'b1111;
wire reset=startup[3];
(* KEEP="TRUE" *) reg [63:0] source_a=64'h123456789abcdef1;
(* KEEP="TRUE" *) reg [31:0] source_b=32'h6b72d901;
(* KEEP="TRUE" *) reg source_valid=0,sink_ready=0;
reg [2:0] stall_cycle=0;
wire in_ready,out_valid;wire [63:0] result;
wire [1:0] b0=source_b[1:0]==2'b10 ? 2'b11 :
                    source_b[1:0]==2'b01 ? 2'b01 : 2'b00;
wire [1:0] b1=source_b[3:2]==2'b10 ? 2'b11 :
                    source_b[3:2]==2'b01 ? 2'b01 : 2'b00;
(* KEEP="TRUE" *) reg [63:0] sink_signature=0;
assign signature=sink_signature;
(* KEEP_HIERARCHY="TRUE" *) SearchTop kernel(kernel_clock,reset,source_valid,in_ready,
source_a,{b1,b0},out_valid,sink_ready,result);
always @(posedge kernel_clock)begin
startup<={startup[2:0],1'b0};
if(reset)begin
source_a<=64'h123456789abcdef1;source_b<=32'h6b72d901;
source_valid<=0;sink_ready<=0;stall_cycle<=0;sink_signature<=0;
end else begin
source_valid<=1;stall_cycle<=stall_cycle+1;sink_ready<=stall_cycle!=3;
if(source_valid && in_ready)begin
source_a<={source_a[62:0],source_a[63]^source_a[62]^source_a[60]^source_a[59]};
source_b<={source_b[30:0],source_b[31]^source_b[21]^source_b[1]^source_b[0]};
end
if(out_valid && sink_ready)sink_signature<={sink_signature[62:0],sink_signature[63]}^result;
end
end
endmodule
'''
    if context==CONTEXT:
        text=text.replace('module TimingHarness(input clock,output [63:0] signature);','module TimingHarness(input clock);\nwire [63:0] signature;')
        text=text.replace('(* KEEP="TRUE" *) reg [63:0] sink_signature=0;', '(* KEEP="TRUE", DONT_TOUCH="TRUE" *) reg [63:0] sink_signature=0;')
    return text


def checks_tcl(directory,quote):
    """Fail closed if synthesis removes the kernel, boundaries, or clock buffer."""
    return f'''set kernel_cells [get_cells -hier -filter {{NAME =~ kernel/*}}]
set source_cells [get_cells -hier -filter {{NAME =~ source_a_reg* || NAME =~ source_b_reg*}}]
set sink_cells [get_cells -hier -filter {{NAME =~ sink_signature_reg*}}]
set buffers [get_cells -hier -filter {{REF_NAME =~ BUFG*}}]
set check_stream [open {quote(directory/'harness-checks.rpt')} w]
puts $check_stream "kernel_cells [llength $kernel_cells]"
puts $check_stream "source_cells [llength $source_cells]"
puts $check_stream "sink_cells [llength $sink_cells]"
puts $check_stream "clock_buffers [llength $buffers]"
puts $check_stream "clocks [llength [get_clocks]]"
close $check_stream
if {{[llength $kernel_cells]<100 || [llength $source_cells]<64 || [llength $sink_cells]<64 || [llength $buffers]<1 || [llength [get_clocks]]!=1}} {{error "timing harness structure was removed"}}
report_clock_utilization -file {quote(directory/'clock-utilization.rpt')}
report_utilization -hierarchical -hierarchical_depth 2 -file {quote(directory/'hierarchical-utilization.rpt')}
'''


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--row',type=Path,required=True)
    p.add_argument('--rtl',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--context',choices=CONTEXTS,default=CONTEXT)
    args=p.parse_args();validate(json.loads(args.row.read_text()),args.rtl,args.output_dir,args.context)
