#!/usr/bin/env python3
"""Check fixed-width SGen stride permutations with an independent matrix oracle."""
import argparse
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,run,source_identity,write_json


def testbench(nbits,kbits,stridebits,dual,lead):
    n,lanes=1<<nbits,1<<kbits;cycles=n//lanes;rows=n//(1<<stridebits);cols=1<<stridebits
    starts=[lead+2]
    for gap in (0,0,1 if dual else cycles,2 if dual else cycles+1,0):starts.append(starts[-1]+cycles+gap)
    finish=starts[-1]+cycles+4*n
    stimulus=[]
    for cycle in range(finish):
        active=next(((frame,cycle-start) for frame,start in enumerate(starts) if start<=cycle<start+cycles),None)
        stimulus.append(f'next={int(cycle in [s-lead for s in starts])};')
        for lane in range(lanes):
            value=active[0]*10000+active[1]*lanes+lane+1 if active else 0
            stimulus.append(f'i{lane}=32\'d{value};')
        stimulus.append('tick;')
    ports=['.clk(clk)','.reset(reset)','.next(next)','.next_out(next_out)']+[f'.i{i}(i{i})' for i in range(lanes)]+[f'.o{i}(o{i})' for i in range(lanes)]
    checks='\n'.join(f'''index=out_cycle*{lanes}+{i};expected=frame*10000+(index%{rows})*{cols}+index/{rows}+1;
if(o{i}!==expected) $fatal(1,"stride frame %d index %d actual %d expected %d",frame,index,o{i},expected);''' for i in range(lanes))
    declarations='\n'.join(f'reg [31:0] i{i}=0;wire [31:0] o{i};' for i in range(lanes))
    return f'''module test;reg clk=0,reset=1,next=0;wire next_out;
{declarations}
main dut({','.join(ports)});
integer frame=0,out_cycle=0,index,expected,epoch;reg checking=0,active=0;
task tick;begin #5;clk=1;#1;
if(checking)begin
 if(next_out)begin if(active) $fatal(1,"overlapping output frames");active=1;out_cycle=0;end
 if(active)begin
  if(frame>=6) $fatal(1,"extra output frame");
  {checks}
  if(out_cycle=={cycles-1})begin active=0;out_cycle=0;frame=frame+1;end else out_cycle=out_cycle+1;
 end
end
#4;clk=0;end endtask
initial begin
for(epoch=0;epoch<2;epoch=epoch+1)begin
 checking=0;reset=1;next=0;tick;tick;reset=0;
 // Drain any unreset token/data pipeline after an aborted input transaction.
 repeat({4*n})tick;
 reset=1;tick;tick;reset=0;frame=0;out_cycle=0;active=0;checking=1;
 {''.join(stimulus)}
 if(frame!=6||active) $fatal(1,"missing output frames %d",frame);
 checking=0;next=1;tick;next=0;tick;tick;
end
$display("PASS fixed-width stride: matrix ordering, continuous frames, legal gaps, reset with drain");$finish;
end endmodule
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sgen-root',type=Path,default=Path(__file__).resolve().parents[2]/'SGen')
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();repo=a.sgen_root.resolve();out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
    results=[]
    for nbits,kbits,stridebits in ((4,1,2),(5,2,2),(6,2,3),(6,3,2)):
        for dual in (False,True):
            work=out/f'n{nbits}-k{kbits}-r{stridebits}-dual{int(dual)}';work.mkdir(parents=True)
            rtl=work/'permutation.v';tb=work/'test.sv';lead=None
            command=['bash',str(repo/'sgen.bat'),'-nologo','-n',str(nbits),'-k',str(kbits),'-r',str(stridebits),'-hw','int','-o',str(rtl)]
            if dual:command+=['-dualRAMcontrol']
            processes=[run(command+['stride'],repo,work/'generate.log',120)]
            if processes[-1]['returncode']==0:
                lead_match=re.search(r'set high (\d+) cycles before the first inputs enter',rtl.read_text())
                if not lead_match:raise ValueError('generated interface does not declare next lead time')
                lead=int(lead_match.group(1));tb.write_text(testbench(nbits,kbits,stridebits,dual,lead))
                processes.append(run(['iverilog','-g2012','-s','test','-o','simulation',str(rtl),str(tb)],work,work/'compile.log',120))
                if processes[-1]['returncode']==0:processes.append(run(['vvp','simulation'],work,work/'test.log',120))
            passed=len(processes)==3 and all(r['returncode']==0 for r in processes)
            results.append({'n':1<<nbits,'lanes':1<<kbits,'matrix_columns':1<<stridebits,'dual_ram_control':dual,'next_lead_cycles':lead,'passed':passed,'processes':processes,'artifacts':{str(f.relative_to(out)):file_hash(f) for f in (rtl,tb) if f.exists()}})
            print(work.name,'PASS' if passed else 'FAIL',flush=True)
    write_json(out/'report.json',{'source':source_identity(repo),'binary_sha256':file_hash(repo/'sgen.bat'),'scope':'Fixed-width stride components, generator-declared advance next signal, uninterrupted frames, legal interframe gaps and reset with 4N-cycle drain. Not a ready/valid or full-NTT comparison.','results':results})
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
