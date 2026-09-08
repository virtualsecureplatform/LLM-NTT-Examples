"""Independent OpenNTT host-memory verification with explicit ordering conversions."""
from __future__ import annotations
import json
from pathlib import Path
import re
import time
from . import oracle
from .model import run, write_json, file_hash
from .evaluate import parse_metrics


def physical_address(index: int,n: int,pe: int,layout: str) -> int:
    depth=n//(2*pe)
    if layout=='nr_input':
        return (2*((index//depth)%pe)+index//(depth*pe))*depth+index%depth
    if layout=='nr_output':
        return (2*((index//2)//depth)+(index%2))*depth+(index//2)%depth
    raise ValueError('unknown OpenNTT memory layout')


def reordered(workload: dict,pe: int) -> tuple[list[list[int]],list[list[int]]]:
    n=workload['n']; bits=n.bit_length()-1
    reverse=lambda i:int(f'{i:0{bits}b}'[::-1],2)
    inverse=workload.get('direction')=='inverse'
    inputs=[];outputs=[]
    for vector in oracle.vectors(workload):
        expected=oracle.transform(vector,workload)
        a=[0]*n;b=[0]*n
        for i in range(n):
            a[physical_address(reverse(i) if inverse else i,n,pe,'nr_output' if inverse else 'nr_input')]=vector[i]
            b[physical_address(i if inverse else reverse(i),n,pe,'nr_input' if inverse else 'nr_output')]=expected[i]
        inputs.append(a);outputs.append(b)
    return inputs,outputs


def testbench(workload: dict,frames: int) -> str:
    n=workload['n'];width=int(workload['q']).bit_length();inverse=workload.get('direction')=='inverse'
    return f'''module oracle_tb;
localparam N={n},W={width},FRAMES={frames};
reg clk=0,rst=1,wen=0;
reg [$clog2(N)-1:0] wa=0,ra=0;
reg [W-1:0] wd=0;wire [W-1:0] rd;wire done;
reg [W-1:0] inputs[0:N*FRAMES-1],expected[0:N*FRAMES-1];
integer frame,i,cycles,compute_cycles;
always #5 clk=~clk;
OpenNTT dut(.clk(clk),.rst(rst),.forward(1'b{0 if inverse else 1}),.opcode(2'd0),
.q({width}'d{workload['q']}),.montgomery_factor({width}'d0),.rom_base_addr('0),
.poly_base_a('0),.poly_base_b('0),.io_ram_wen(wen),.io_ram_waddr(wa),.io_ram_raddr(ra),.io_ram_wdata(wd),.io_ram_rdata(rd),.done(done));
initial begin
 $readmemh("inputs.mem",inputs);$readmemh("expected.mem",expected);
 for(frame=0;frame<FRAMES;frame=frame+1) begin
  rst=1;wen=0;repeat(64) @(negedge clk);
  for(i=0;i<N;i=i+1) begin
   wa=i;wd=inputs[frame*N+i];wen=1;@(negedge clk);
  end
  wen=0;repeat(8) @(negedge clk);
  for(i=0;i<N;i=i+1) begin
   ra=i;repeat(6) @(negedge clk);
   if(rd !== inputs[frame*N+i]) $fatal(1,"OpenNTT host load mismatch frame=%0d physical=%0d got=%0d expected=%0d",frame,i,rd,inputs[frame*N+i]);
  end
  rst=0;
  for(cycles=0;cycles<{n*100+1000} && !done;cycles=cycles+1) @(negedge clk);
  if(!done) $fatal(1,"OpenNTT compute timeout");
  compute_cycles=cycles;
  // rst selects host ownership of coefficient RAM; it does not clear RAM.
  repeat(8) @(negedge clk);rst=1;
  for(i=0;i<N;i=i+1) begin
   ra=i;repeat(6) @(negedge clk);
   if(rd !== expected[frame*N+i]) $fatal(1,"OpenNTT mismatch frame=%0d physical=%0d got=%0d expected=%0d",frame,i,rd,expected[frame*N+i]);
  end
  if(frame==0) $display("METRIC compute_cycles=%0d",compute_cycles);
 end
 $display("METRIC completed_frames=%0d",FRAMES);
 $display("PASS independent OpenNTT");$finish;
end
endmodule
'''



def verified_record(directory: Path) -> dict:
    record=json.loads((directory/'record.json').read_text());w=record['workload'];oracle.validate(w)
    if record['process']['returncode']!=0:raise ValueError('OpenNTT generation failed')
    for relative,expected_hash in record['artifacts'].items():
        if file_hash(directory/relative)!=expected_hash:
            raise ValueError(f'baseline artifact changed: {relative}')
    package=(directory/'hardware/open_ntt_pkg.sv').read_text()
    for name,expected_value in {'LOGN':w['n'].bit_length()-1,'LOGQ':int(w['q']).bit_length(),'Q_VALUE':int(w['q']),'PE':record['configuration']['pe']}.items():
        match=re.search(r'localparam (?:\[LOGQ-1:0\] )?'+name+r" = (?:[0-9]+'d)?([0-9]+);",package)
        if not match or int(match.group(1))!=expected_value:
            raise ValueError(f'OpenNTT realized {name} does not match requested workload')
    return record

def evaluate(directory: Path,timeout: float=600) -> dict:
    record=verified_record(directory);w=record['workload'];pe=record['configuration']['pe']
    work=directory/'independent';work.mkdir(exist_ok=True)
    inputs,outputs=reordered(w,pe)
    for name,corpus in [('inputs',inputs),('expected',outputs)]:
        (work/f'{name}.mem').write_text(''.join(f'{x:x}\n' for frame in corpus for x in frame))
    (work/'oracle_tb.sv').write_text(testbench(w,len(inputs)))
    hardware=directory/'hardware'
    packages=[hardware/'floating_point/FLP_pkg.sv',hardware/'intmul/intmul_pkg.sv',hardware/'open_ntt_pkg.sv']
    sources=packages+[p for p in sorted(hardware.rglob('*.sv')) if p not in packages and 'CryptoCore' not in p.parts]
    start=time.monotonic()
    version=run(['verilator','--version'],work,work/'verilator-version.log',min(10,timeout))
    build=run(['verilator','--binary','--timing','--top-module','oracle_tb','-Wno-fatal','-j','4',*[str(p) for p in sources],'oracle_tb.sv'],work,work/'build.log',timeout)
    simulation=run([str(work/'obj_dir/Voracle_tb')],work,work/'simulation.log',max(0,timeout-(time.monotonic()-start))) if build['returncode']==0 else {}
    log=(work/'simulation.log').read_text() if (work/'simulation.log').exists() else ''
    result={'correct':simulation.get('returncode')==0 and 'PASS independent OpenNTT' in log and '$readmem file not found' not in log,'simulator_version':(work/'verilator-version.log').read_text().strip(),'build':build,'simulation':simulation,'metrics':parse_metrics(log),
            'boundary':'scalar host RAM, physical ordering explicitly converted; compute cycles exclude host transfers',
            'comparison_eligible':False}
    result['verification']={str(p):file_hash(p) for p in (work/('test.sv' if (work/'test.sv').exists() else 'oracle_tb.sv'),work/'inputs.mem',work/'expected.mem',Path(oracle.__file__))}
    write_json(work/'results.json',result)
    return result


def stream_wrapper(workload: dict,lanes: int,pe: int) -> str:
    """Normalize the scalar RAM port to the workload's ready/valid stream.

    Capture and load keep the core reset asserted while its control pipelines
    drain, so no artificial startup delay is inserted.
    Two full-frame buffers, serial host transfers, and ordering logic are
    deliberately inside the measured design. Host reads issue every cycle.
    """
    n=workload['n'];bits=n.bit_length()-1;width=int(workload['q']).bit_length()
    inverse=workload.get('direction')=='inverse';depth=n//(2*pe)
    ports=',\n'.join(f'input [{width-1}:0] i{k},output [{width-1}:0] o{k}' for k in range(lanes))
    # One physical bank per stream lane: one write port and synchronous read.
    buffers='\n'.join(f"(* ram_style=\"block\" *) reg [{width-1}:0] input_bank_{k}[0:N/LANES-1],output_bank_{k}[0:N/LANES-1]; reg [{width-1}:0] input_data_{k},output_data_{k};" for k in range(lanes))
    output='\n'.join(f'assign o{k}=output_data_{k};' for k in range(lanes))
    memory='\n'.join(f"""always @(posedge clock) begin
 if(!reset && state==CAPTURE && in_valid)input_bank_{k}[count/LANES]<=i{k};
 if(!reset && (state==LOAD_PREFETCH || state==LOAD))input_data_{k}<=input_bank_{k}[load_prefetch_index/LANES];
 if(!reset && read_valid[3] && read_index[3]%LANES=={k})output_bank_{k}[read_index[3]/LANES]<=host_data;
 if(!reset && (state==OUTPUT_PREFETCH || (state==OUTPUT && out_ready)))output_data_{k}<=output_bank_{k}[output_prefetch_index/LANES];
end""" for k in range(lanes))
    input_mux=' '.join(f'{k}:host_write_data=input_data_{k};' for k in range(lanes))
    write_address='nr_output(reverse_bits(count))' if inverse else 'nr_input(count)'
    read_address='nr_input(count)' if inverse else 'nr_output(reverse_bits(count))'
    return f'''module SearchTop(input clock,reset,in_valid,output in_ready,output out_valid,input out_ready,
{ports});
localparam N={n},LANES={lanes},W={width},DEPTH={depth},PE={pe};
localparam CAPTURE=1,LOAD=2,DRAIN=3,COMPUTE=4,FINISH=5,READ=6,READ_DRAIN=7,OUTPUT=8,LOAD_PREFETCH=9,OUTPUT_PREFETCH=10;
reg [3:0] state;
{buffers}
reg [{width-1}:0] host_write_data;
integer load_lane;
wire [{bits-1}:0] load_prefetch_index=(state==LOAD && count<N-1)?count+1:0;
wire [{bits-1}:0] output_prefetch_index=(state==OUTPUT && count<N-LANES)?count+LANES:0;
always @(*)begin host_write_data=0;case(load_lane){input_mux}default:begin end endcase end
{memory}
integer count,delay_count,k;
reg [3:0] read_valid;
reg [{bits-1}:0] read_index[0:3];
wire [{width-1}:0] host_data;wire done;
wire core_reset=reset || (state!=COMPUTE && state!=FINISH);
wire [{bits-1}:0] write_address={write_address};
wire [{bits-1}:0] read_address={read_address};
assign in_ready=!reset && state==CAPTURE;
assign out_valid=!reset && state==OUTPUT;
{output}
function automatic [{bits-1}:0] reverse_bits(input [{bits-1}:0] value);
 integer b;begin for(b=0;b<{bits};b=b+1)reverse_bits[b]=value[{bits-1}-b];end
endfunction
function automatic [{bits-1}:0] nr_input(input [{bits-1}:0] value);
 begin nr_input=(2*((value/DEPTH)%PE)+value/(DEPTH*PE))*DEPTH+value%DEPTH;end
endfunction
function automatic [{bits-1}:0] nr_output(input [{bits-1}:0] value);
 begin nr_output=(2*((value/2)/DEPTH)+(value%2))*DEPTH+(value/2)%DEPTH;end
endfunction
OpenNTT core(.clk(clock),.rst(core_reset),.forward(1'b{0 if inverse else 1}),.opcode(2'd0),
.q({width}'d{workload['q']}),.montgomery_factor({width}'d0),.rom_base_addr('0),.poly_base_a('0),.poly_base_b('0),
.io_ram_wen(!reset && state==LOAD),.io_ram_waddr(write_address),.io_ram_wdata(host_write_data),
.io_ram_raddr(read_address),.io_ram_rdata(host_data),.done(done));
always @(posedge clock) begin
 if(reset) begin state<=CAPTURE;count<=0;delay_count<=0;read_valid<=0;end
 else begin
  read_valid<={{read_valid[2:0],state==READ}};
  if(state==LOAD_PREFETCH || state==LOAD)load_lane<=load_prefetch_index%LANES;
  read_index[0]<=count;
  for(k=1;k<4;k=k+1)read_index[k]<=read_index[k-1];
  if(read_valid[3]) begin
   if(read_index[3]==N-1)begin state<=OUTPUT_PREFETCH;count<=0;end
  end
  case(state)
   CAPTURE: if(in_valid)begin if(count==N-LANES)begin state<=LOAD_PREFETCH;count<=0;end else count<=count+LANES;end
   LOAD_PREFETCH: state<=LOAD;
   OUTPUT_PREFETCH: state<=OUTPUT;
   LOAD: if(count==N-1)begin state<=DRAIN;count<=0;delay_count<=0;end else count<=count+1;
   DRAIN: if(delay_count==7)state<=COMPUTE;else delay_count<=delay_count+1;
   COMPUTE: if(done)begin state<=FINISH;delay_count<=0;end
   FINISH: if(delay_count==7)begin state<=READ;count<=0;end else delay_count<=delay_count+1;
   READ: if(count==N-1)begin state<=READ_DRAIN;count<=0;end else count<=count+1;
   OUTPUT: if(out_ready)begin if(count==N-LANES)begin state<=CAPTURE;count<=0;end else count<=count+LANES;end
   default: begin end
  endcase
 end
end
endmodule
'''


def evaluate_stream(directory: Path,timeout: float=600) -> dict:
    from .evaluate import generic_testbench
    from .boundary import registered_ready_valid
    record=verified_record(directory);w=record['workload']
    work=directory/'stream';work.mkdir(exist_ok=True);lanes=w.get('lanes',4)
    if lanes<1 or lanes&(lanes-1) or w['n']%lanes:raise ValueError('invalid external lane count')
    rtl=registered_ready_valid(stream_wrapper(w,lanes,record['configuration']['pe']),lanes,int(w['q']).bit_length())
    (work/'SearchTop.sv').write_text(rtl)
    inputs=oracle.vectors(w)
    for name,corpus in [('inputs',inputs),('expected',[oracle.transform(v,w) for v in inputs])]:
        (work/f'{name}.mem').write_text(''.join(f'{x:x}\n' for frame in corpus for x in frame))
    (work/'test.sv').write_text(generic_testbench(w,lanes,len(inputs),max(10000,w['n']*w['n'].bit_length()*64)))
    hardware=directory/'hardware'
    packages=[hardware/'floating_point/FLP_pkg.sv',hardware/'intmul/intmul_pkg.sv',hardware/'open_ntt_pkg.sv']
    sources=packages+[p for p in sorted(hardware.rglob('*.sv')) if p not in packages and 'CryptoCore' not in p.parts]
    start=time.monotonic()
    version=run(['verilator','--version'],work,work/'verilator-version.log',min(10,timeout))
    build=run(['verilator','--binary','--timing','--top-module','test','-Wno-fatal','-j','4',*[str(p) for p in sources],'SearchTop.sv','test.sv'],work,work/'build.log',timeout)
    simulation=run([str(work/'obj_dir/Vtest')],work,work/'simulation.log',max(0,timeout-(time.monotonic()-start))) if build['returncode']==0 else {}
    log=(work/'simulation.log').read_text() if (work/'simulation.log').exists() else ''
    result={'correct':simulation.get('returncode')==0 and 'PASS generic NTT' in log and '$readmem file not found' not in log,
            'simulator_version':(work/'verilator-version.log').read_text().strip(),'build':build,'simulation':simulation,'metrics':parse_metrics(log),'mode':'functional',
            'boundary':{'kind':'registered-ready-valid','lanes':lanes,'adapter_coefficient_buffers':2,'host_coefficients_per_cycle':1},
            'rtl':str(work/'SearchTop.sv'),'rtl_hash':file_hash(work/'SearchTop.sv'),'sources':[str(p) for p in sources]}
    result['verification']={str(p):file_hash(p) for p in (work/('test.sv' if (work/'test.sv').exists() else 'oracle_tb.sv'),work/'inputs.mem',work/'expected.mem',Path(oracle.__file__))}
    write_json(work/'results.json',result)
    return result
