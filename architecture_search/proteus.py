"""Independent Proteus OP1 verification and explicit SDF/MDC memory ordering."""
from __future__ import annotations
import json
from pathlib import Path
import re
import time
from . import oracle
from .model import file_hash,run,write_json
from .evaluate import parse_metrics


def verified_record(directory: Path) -> dict:
    record=json.loads((directory/'record.json').read_text());oracle.validate(record['workload'])
    if record['process']['returncode']!=0:raise ValueError('Proteus generation failed')
    for relative,expected in record['artifacts'].items():
        if file_hash(directory/relative)!=expected:raise ValueError(f'Proteus artifact changed: {relative}')
    return record


def memory_index(index: int,n: int,architecture: str,spectral: bool) -> int:
    if not spectral:return index
    bits=n.bit_length()-1
    if architecture=='mdc':index=2*(index%(n//2))+index//(n//2)
    return int(f'{index:0{bits}b}'[::-1],2)


def sources(directory: Path) -> list[Path]:
    return [p for p in sorted((directory/'hardware').rglob('*')) if p.suffix in ('.v','.sv') and '_tb' not in p.stem]


def drain_cycles(record: dict) -> int:
    """Conservative bound for unreset start/finish delay lines across all stages."""
    p=record['parameters'];n=record['workload']['n']
    stage=sum(int(p[k]) for k in ('DELAY_ADD','DELAY_MUL','DELAY_RED','DELAY_DIV2'))+4
    return n+16+(n.bit_length()-1)*stage


def testbench(w: dict,architecture: str,frames: int,reset_cycles: int) -> str:
    n=w['n'];width=int(w['q']).bit_length();ab=max(10,n.bit_length()-1);streams=2 if architecture=='mdc' else 1;beats=n//streams
    declarations='\n'.join(f'reg [{width-1}:0] din{k};wire [{width-1}:0] dout{k};' for k in range(streams))
    connections=','.join(f'.data64_in{"_"+str(k) if streams==2 else ""}(din{k}),.data64_out{"_"+str(k) if streams==2 else ""}(dout{k})' for k in range(streams))
    drive=' '.join(f'din{k}<=inputs[frame*N+ra+{k*beats}];' for k in range(streams))
    check=' '.join(f'if(dout{k} !== expected[frame*N+wa+{k*beats}])$fatal(1,"Proteus mismatch frame=%0d addr=%0d lane={k} got=%0d expected=%0d",frame,wa,dout{k},expected[frame*N+wa+{k*beats}]);' for k in range(streams))
    return f'''module oracle_tb;
localparam N={n},BEATS={beats},FRAMES={frames};
reg clk=0,rst=1,start=0;wire finish,wea;
wire [{ab-1}:0] ra,wa;
{declarations}
reg [{width-1}:0] inputs[0:N*FRAMES-1],expected[0:N*FRAMES-1];
integer frame,cycle,received,first_cycle;
always #5 clk=~clk;
ntt_memory_wrapper core(.clk(clk),.rst(rst),.start(start),.intt(1'b{int(w.get('direction')=='inverse')}),.btf_gs(1'b{int(w.get('direction')=='inverse')}),
.read_address(ra),.write_address(wa),.wea(wea),.q({width}'d{w['q']}),.finish(finish),{connections});
always @(posedge clk)begin if(ra<BEATS)begin {drive} end end
initial begin
 $readmemh("inputs.mem",inputs);$readmemh("expected.mem",expected);
 for(frame=0;frame<FRAMES;frame=frame+1)begin
  rst=1;start=0;repeat({reset_cycles})@(negedge clk);rst=0;start=1;received=0;first_cycle=-1;
  for(cycle=0;cycle<{n*100+10000} && received<BEATS;cycle=cycle+1)begin
   @(posedge clk);
   if(wea)begin
    if(wa!=received)$fatal(1,"Proteus output address mismatch");
    {check}
    if(first_cycle<0)first_cycle=cycle;
    received=received+1;
   end
   @(negedge clk);
  end
  if(received!=BEATS)$fatal(1,"Proteus timeout received=%0d",received);
  if(frame==0)begin
   $display("METRIC first_output_cycles=%0d",first_cycle);
   $display("METRIC transaction_cycles=%0d",cycle);
  end
 end
 $display("METRIC completed_frames=%0d",FRAMES);
 $display("PASS independent Proteus");$finish;
end
endmodule
'''


def evaluate(directory: Path,timeout: float=600,simulator: str='verilator') -> dict:
    record=verified_record(directory);w=record['workload'];architecture=record['configuration']['architecture'];n=w['n']
    work=directory/'independent';work.mkdir(exist_ok=True)
    vectors=oracle.vectors(w);inverse=w.get('direction')=='inverse'
    for name,corpus,spectral in [('inputs',vectors,inverse),('expected',[oracle.transform(v,w) for v in vectors],not inverse)]:
        (work/f'{name}.mem').write_text(''.join(f'{frame[memory_index(i,n,architecture,spectral)]:x}\n' for frame in corpus for i in range(n)))
    (work/'oracle_tb.sv').write_text(testbench(w,architecture,len(vectors),drain_cycles(record)))
    start=time.monotonic()
    run(['verilator','--version'] if simulator=='verilator' else ['iverilog','-V'],work,work/'version.log',min(10,timeout))
    command=['verilator','--binary','--timing','--top-module','oracle_tb','-Wno-fatal','-j','4'] if simulator=='verilator' else ['iverilog','-g2012','-s','oracle_tb','-o','simulation']
    build=run([*command,'-I'+str(directory/'hardware'),*[str(p) for p in sources(directory)],'oracle_tb.sv'],work,work/'build.log',timeout)
    simulation=run([str(work/'obj_dir/Voracle_tb')] if simulator=='verilator' else ['vvp',str(work/'simulation')],work,work/'simulation.log',max(0,timeout-(time.monotonic()-start))) if build['returncode']==0 else {}
    log=(work/'simulation.log').read_text() if (work/'simulation.log').exists() else ''
    result={'correct':simulation.get('returncode')==0 and 'PASS independent Proteus' in log,'build':build,'simulation':simulation,'metrics':parse_metrics(log),
            'simulator_version':(work/'version.log').read_text().strip(),'boundary':'Proteus memory-wrapper protocol, external frame memory not yet included','comparison_eligible':False,
            'verification':{str(p):file_hash(p) for p in (work/'oracle_tb.sv',work/'inputs.mem',work/'expected.mem',Path(oracle.__file__))}}
    write_json(work/'results.json',result)
    return result


def stream_wrapper(record: dict,lanes: int) -> str:
    w=record['workload'];n=w['n'];bits=n.bit_length()-1;width=int(w['q']).bit_length()
    architecture=record['configuration']['architecture'];streams=2 if architecture=='mdc' else 1
    beats=n//streams;ab=max(10,bits);inverse=w.get('direction')=='inverse'
    ports=',\n'.join(f'input [{width-1}:0] i{k},output [{width-1}:0] o{k}' for k in range(lanes))
    capture=' '.join(f'input_buffer[count+{k}]<=i{k};' for k in range(lanes))
    output='\n'.join(f'assign o{k}=output_buffer[count+{k}];' for k in range(lanes))
    declarations='\n'.join(f'reg [{width-1}:0] din{k};wire [{width-1}:0] dout{k};' for k in range(streams))
    connections=','.join(f'.data64_in{"_"+str(k) if streams==2 else ""}(din{k}),.data64_out{"_"+str(k) if streams==2 else ""}(dout{k})' for k in range(streams))
    def address(value,k,spectral):
        value=f'({value}+{k*beats})'
        if spectral:
            if streams==2:value=f'(2*({value}%BEATS)+{value}/BEATS)'
            value=f'reverse_bits({value})'
        return value
    read=' '.join(f'din{k}<=input_buffer[{address("ra",k,inverse)}];' for k in range(streams))
    write=' '.join(f'output_buffer[{address("wa",k,not inverse)}]<=dout{k};' for k in range(streams))
    return f'''module SearchTop(input clock,reset,in_valid,output in_ready,output out_valid,input out_ready,
{ports});
localparam N={n},BEATS={beats},LANES={lanes},DRAIN_CYCLES={drain_cycles(record)};
localparam CAPTURE=0,DRAIN=1,COMPUTE=2,OUTPUT=3;
reg [1:0] state;
reg [{width-1}:0] input_buffer[0:N-1],output_buffer[0:N-1];
integer count,drained;
wire [{ab-1}:0] ra,wa;
wire wea,finish;
{declarations}
wire core_reset=reset || state!=COMPUTE;
assign in_ready=!reset && state==CAPTURE;
assign out_valid=!reset && state==OUTPUT;
{output}
function automatic [{bits-1}:0] reverse_bits(input [{bits-1}:0] value);
 integer b;begin for(b=0;b<{bits};b=b+1)reverse_bits[b]=value[{bits-1}-b];end
endfunction
ntt_memory_wrapper core(.clk(clock),.rst(core_reset),.start(!core_reset),
.intt(1'b{int(inverse)}),.btf_gs(1'b{int(inverse)}),.read_address(ra),.write_address(wa),
.wea(wea),.q({width}'d{w['q']}),.finish(finish),{connections});
// The upstream wrapper expects a synchronous, one-cycle external RAM read.
always @(posedge clock)begin if(ra<BEATS)begin {read} end end
always @(posedge clock)begin
 if(reset)begin state<=CAPTURE;count<=0;drained<=0;end
 else begin
  if(state==COMPUTE)drained<=0;
  else if(drained<DRAIN_CYCLES)drained<=drained+1;
  case(state)
   CAPTURE: if(in_valid)begin {capture}
    if(count==N-LANES)begin count<=0;state<=DRAIN;end else count<=count+LANES;
   end
   DRAIN: if(drained==DRAIN_CYCLES)state<=COMPUTE;
   COMPUTE: if(wea)begin {write} if(wa==BEATS-1)begin state<=OUTPUT;count<=0;end end
   OUTPUT: if(out_ready)begin
    if(count==N-LANES)begin count<=0;state<=CAPTURE;end else count<=count+LANES;
   end
  endcase
 end
end
endmodule
'''


def evaluate_stream(directory: Path,timeout: float=600,simulator: str='verilator') -> dict:
    from .evaluate import generic_testbench
    from .boundary import registered_ready_valid
    record=verified_record(directory);w=record['workload'];lanes=w.get('lanes',4)
    if lanes<1 or lanes&(lanes-1) or w['n']%lanes:raise ValueError('invalid external lane count')
    work=directory/'stream';work.mkdir(exist_ok=True)
    (work/'SearchTop.sv').write_text(registered_ready_valid(stream_wrapper(record,lanes),lanes,int(w['q']).bit_length()))
    vectors=oracle.vectors(w)
    for name,corpus in [('inputs',vectors),('expected',[oracle.transform(v,w) for v in vectors])]:
        (work/f'{name}.mem').write_text(''.join(f'{x:x}\n' for frame in corpus for x in frame))
    (work/'test.sv').write_text(generic_testbench(w,lanes,len(vectors),max(10000,w['n']*w['n'].bit_length()*64)))
    start=time.monotonic()
    run(['verilator','--version'] if simulator=='verilator' else ['iverilog','-V'],work,work/'version.log',min(10,timeout))
    rtl_sources=sources(directory)
    command=['verilator','--binary','--timing','--top-module','test','-Wno-fatal','-j','4'] if simulator=='verilator' else ['iverilog','-g2012','-s','test','-o','simulation']
    build=run([*command,'-I'+str(directory/'hardware'),*[str(p) for p in rtl_sources],'SearchTop.sv','test.sv'],work,work/'build.log',timeout)
    simulation=run([str(work/'obj_dir/Vtest')] if simulator=='verilator' else ['vvp',str(work/'simulation')],work,work/'simulation.log',max(0,timeout-(time.monotonic()-start))) if build['returncode']==0 else {}
    log=(work/'simulation.log').read_text() if (work/'simulation.log').exists() else ''
    result={'correct':simulation.get('returncode')==0 and 'PASS generic NTT' in log,'build':build,'simulation':simulation,'metrics':parse_metrics(log),'mode':'functional',
            'simulator_version':(work/'version.log').read_text().strip(),
            'boundary':{'kind':'registered-ready-valid','lanes':lanes,'adapter_coefficient_buffers':2,'core_coefficients_per_cycle':2 if record['configuration']['architecture']=='mdc' else 1,'reset_drain_cycles':drain_cycles(record)},
            'rtl':str(work/'SearchTop.sv'),'rtl_hash':file_hash(work/'SearchTop.sv'),'sources':[str(p) for p in rtl_sources],
            'verification':{str(p):file_hash(p) for p in (work/'test.sv',work/'inputs.mem',work/'expected.mem',Path(oracle.__file__))}}
    write_json(work/'results.json',result)
    return result
