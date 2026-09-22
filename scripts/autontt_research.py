#!/usr/bin/env python3
"""Prepare pinned AutoNTT traces and field-matched NGen campaigns."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import autontt_research as study
from architecture_search.model import write_json,artifact_manifest
ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['probe','trace','prepare-ngen','compare'],required=True)
    p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--design',type=Path)
    p.add_argument('--architecture',choices=['I','D','H']);p.add_argument('--trace',type=Path)
    p.add_argument('--left',type=Path);p.add_argument('--right',type=Path);a=p.parse_args(argv)
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.stage=='probe':
        results=[]
        for n,bits,reduction in [(1024,64,'C'),(16384,54,'B')]:
            for arch in ('I','D','H'):
                directory=out/f'{n}-{arch}';directory.mkdir(exist_ok=True)
                command=[sys.executable,str(ROOT/'scripts/run_autontt_hls_harness.py'),'--poly-size',str(n),
                    '--mod-size',str(bits),'--modmul-type',reduction,'--custom-bu-mode','probe','--parallel-limbs','1',
                    '--arch-type',arch,'--output-root',str(directory)]
                with (directory/'driver.log').open('w') as log:
                    code=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=21600).returncode
                results.append(dict(n=n,architecture=arch,returncode=code,directory=str(directory)))
                write_json(out/'probes.json',dict(complete=len(results)==6 and all(r['returncode']==0 for r in results),runs=results,
                    scope='Code generation and custom BU probe; whole-kernel matched measurements remain separate.'))
        return int(any(r['returncode'] for r in results))
    if a.stage=='trace':
        if a.design is None or a.architecture is None:p.error('--design and --architecture required')
        d=out/'csim'
        if d.exists():raise ValueError('existing C-simulation directory')
        shutil.copytree(a.design,d)
        host=d/'ntt_test.cpp';host.write_text(study.instrument_host(host.read_text()))
        with (d/'build.log').open('w') as log:
            subprocess.run(['make','csim_compile','XILINX_HLS=/home/opt/xilinx/Vitis_HLS/2023.2'],cwd=d,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200)
        with (d/'trace.log').open('w') as log:subprocess.run(['./ntt'],cwd=d,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600)
        result=study.verify_trace((d/'trace.log').read_text(),a.architecture)
        result['artifacts']=artifact_manifest([host,d/'ntt_kernel.cpp',d/'ntt.h',d/'trace.log'])
        write_json(out/'trace.json',result);return 0
    if a.stage=='prepare-ngen':
        if a.trace is None:p.error('--trace required')
        trace=json.loads(a.trace.read_text())
        for direction in ('forward','inverse'):write_json(out/(direction+'.json'),study.matched_campaign(trace,direction))
        return 0
    if a.left is None or a.right is None:p.error('--left and --right required')
    write_json(out/'comparison.json',study.compare(json.loads(a.left.read_text()),json.loads(a.right.read_text())));return 0

if __name__=='__main__':raise SystemExit(main())
