#!/usr/bin/env python3
"""Verify SGen width-changing transposes under their serialized frame contract."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,run,source_identity,write_json


def testbench(rows,cols):
    # Row-major input -> column-major output, derived directly from matrix indices.
    schedule=[]
    def cycle(reset=False,start=False,inputs=None,outputs=None,first=False):
        schedule.append((reset,start,inputs,outputs,first))
    cycle(True);cycle(True)
    # Abort a partly captured matrix, then ensure the next frame is independent.
    cycle(start=True,inputs=[0xdead0000+c for c in range(cols)])
    cycle(True);cycle(True)
    for frame,gap in enumerate((0,0,1,2,7,0)):
        matrix=[[frame*10000+r*cols+c+1 for c in range(cols)] for r in range(rows)]
        for r in range(rows):cycle(start=r==0,inputs=matrix[r])
        for c in range(cols):cycle(outputs=[matrix[r][c] for r in range(rows)],first=c==0)
        for _ in range(gap):cycle()
    for _ in range(rows+cols):cycle()
    body=[]
    for index,(reset,start,inputs,outputs,first) in enumerate(schedule):
        body.append(f'reset={int(reset)};next={int(start)};')
        body += [f'i{c}=32\'d{v};' for c,v in enumerate(inputs or [0]*cols)]
        body.append('#5;clk=1;#1;')
        body.append(f'if(next_out!==1\'b{int(first)}) $fatal(1,"next_out cycle {index}");')
        if outputs:
            body += [f'if(o{r}!==32\'d{v}) $fatal(1,"matrix output cycle {index}, lane {r}: %d",o{r});' for r,v in enumerate(outputs)]
        body.append('#4;clk=0;')
    ports=['.clk(clk)','.reset(reset)','.next(next)','.next_out(next_out)']+[f'.i{c}(i{c})' for c in range(cols)]+[f'.o{r}(o{r})' for r in range(rows)]
    declarations=[f'reg [31:0] i{c}=0;' for c in range(cols)]+[f'wire [31:0] o{r};' for r in range(rows)]
    return 'module test; reg clk=0,reset=1,next=0;wire next_out;\n'+'\n'.join(declarations)+'\nswitchtranspose dut('+','.join(ports)+');\ninitial begin\n'+'\n'.join(body)+'\n$display("PASS rectangular transpose: six frames, reset abort, minimum legal interval and gaps");$finish;end endmodule\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sgen-root',type=Path,default=Path(__file__).resolve().parents[2]/'SGen')
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();repo=a.sgen_root.resolve();out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
    results=[]
    for rowlog in (1,2,3,4):
        for collog in (1,2,3,4):
            if rowlog==collog:continue
            rows,cols=1<<rowlog,1<<collog;work=out/f'{rows}x{cols}';work.mkdir(parents=True)
            rtl=work/'permutation.v';tb=work/'test.sv';tb.write_text(testbench(rows,cols))
            processes=[run(['bash',str(repo/'sgen.bat'),'-nologo','-n',str(rowlog+collog),'-k',str(collog),'-hw','int','-o',str(rtl),'switchtranspose'],repo,work/'generate.log',120)]
            if processes[-1]['returncode']==0:
                processes.append(run(['iverilog','-g2012','-s','test','-o','simulation',str(rtl),str(tb)],work,work/'compile.log',120))
                if processes[-1]['returncode']==0:processes.append(run(['vvp','simulation'],work,work/'test.log',120))
            passed=len(processes)==3 and all(r['returncode']==0 for r in processes)
            results.append({'rows':rows,'columns':cols,'passed':passed,'input_lanes':cols,'output_lanes':rows,'first_output_cycles':rows,'minimum_frame_interval_cycles':rows+cols,'processes':processes,'artifacts':{str(f.relative_to(out)):file_hash(f) for f in (rtl,tb) if f.exists()}})
            print(rows,cols,'PASS' if passed else 'FAIL',flush=True)
    write_json(out/'report.json',{'source':source_identity(repo),'binary_sha256':file_hash(repo/'sgen.bat'),'scope':'Rectangular memory-backed width-changing SGen component. Input frames cannot overlap output serialization; gaps are legal only between complete transactions. Not a fixed-width full-throughput switch or complete NTT comparison.','results':results})
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
