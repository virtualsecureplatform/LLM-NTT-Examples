#!/usr/bin/env python3
"""Compare square NGen/SGen switch networks against one cycle-accurate oracle."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import run, source_identity, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    root=Path(__file__).resolve().parents[2]
    p.add_argument('--ngen-root',type=Path,default=root/'NGen')
    p.add_argument('--sgen-root',type=Path,default=root/'SGen')
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args(); out=args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
    results=[]
    for bits in (1,2,3,4,5):
        for name,repo in [('ngen',args.ngen_root.resolve()),('sgen',args.sgen_root.resolve())]:
            work=out/f'{name}-{bits}';work.mkdir(parents=True)
            rtl=work/'permutation.sv'
            if name=='ngen':
                command=['bash',str(repo/'ngen.bat'),'-n',str(bits),'-data-width','32','-top','SwitchTransposeStream','-o',str(rtl),'switchtranspose']
            else:
                command=['bash',str(repo/'sgen.bat'),'-nologo','-n',str(2*bits),'-k',str(bits),'-hw','int','-o',str(rtl),'switchtranspose']
            processes=[run(command,repo,work/'generation.log',120)]
            if processes[-1]['returncode']==0:
                if name=='sgen':
                    with rtl.open('a') as f:
                        f.write(f'\nmodule SwitchTransposeStream(input clock,reset,valid_in,input [{32*(1<<bits)-1}:0] data_in,output valid_out,output [{32*(1<<bits)-1}:0] data_out);\nSGenSwitchTransposeNetwork_{bits}_32 dut(clock,reset,valid_in,data_in,valid_out,data_out);\nendmodule\n')
                processes.append(run(['iverilog','-g2012','-s','switch_transpose_stream_tb','-P',f'switch_transpose_stream_tb.LOG_SIZE={bits}','-o','sim',str(rtl),str(args.ngen_root.resolve()/'tests/rtl/switch_transpose_stream_tb.sv')],work,work/'compile.log',120))
                if processes[-1]['returncode']==0:
                    processes.append(run(['vvp','sim'],work,work/'test.log',120))
            passed=len(processes)==3 and all(x['returncode']==0 for x in processes)
            results.append({'generator':name,'lanes':1<<bits,'passed':passed,'processes':processes})
            print(name,1<<bits,'PASS' if passed else 'FAIL',flush=True)
    write_json(out/'report.json',{'scope':'square permutation components, uninterrupted frames with arbitrary inter-frame gaps; not a complete NTT baseline','sources':{'ngen':source_identity(args.ngen_root),'sgen':source_identity(args.sgen_root)},'results':results})
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
