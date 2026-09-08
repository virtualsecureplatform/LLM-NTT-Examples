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


def testbench(w: dict,architecture: str,frames: int) -> str:
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
  rst=1;start=0;repeat(64)@(negedge clk);rst=0;start=1;received=0;first_cycle=-1;
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


def evaluate(directory: Path,timeout: float=600) -> dict:
    record=verified_record(directory);w=record['workload'];architecture=record['configuration']['architecture'];n=w['n']
    work=directory/'independent';work.mkdir(exist_ok=True)
    vectors=oracle.vectors(w);inverse=w.get('direction')=='inverse'
    for name,corpus,spectral in [('inputs',vectors,inverse),('expected',[oracle.transform(v,w) for v in vectors],not inverse)]:
        (work/f'{name}.mem').write_text(''.join(f'{frame[memory_index(i,n,architecture,spectral)]:x}\n' for frame in corpus for i in range(n)))
    (work/'oracle_tb.sv').write_text(testbench(w,architecture,len(vectors)))
    start=time.monotonic()
    run(['verilator','--version'],work,work/'version.log',min(10,timeout))
    build=run(['verilator','--binary','--timing','--top-module','oracle_tb','-Wno-fatal','-j','4','-I'+str(directory/'hardware'),*[str(p) for p in sources(directory)],'oracle_tb.sv'],work,work/'build.log',timeout)
    simulation=run([str(work/'obj_dir/Voracle_tb')],work,work/'simulation.log',max(0,timeout-(time.monotonic()-start))) if build['returncode']==0 else {}
    log=(work/'simulation.log').read_text() if (work/'simulation.log').exists() else ''
    result={'correct':simulation.get('returncode')==0 and 'PASS independent Proteus' in log,'build':build,'simulation':simulation,'metrics':parse_metrics(log),
            'simulator_version':(work/'version.log').read_text().strip(),'boundary':'Proteus memory-wrapper protocol, external frame memory not yet included','comparison_eligible':False,
            'verification':{str(p):file_hash(p) for p in (work/'oracle_tb.sv',work/'inputs.mem',work/'expected.mem',Path(oracle.__file__))}}
    write_json(work/'results.json',result)
    return result
