#!/usr/bin/env python3
"""Prepare pinned AutoNTT traces and field-matched NGen campaigns."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import autontt_research as study
from architecture_search.model import write_json,artifact_manifest
ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['probe','field','trace','prepare-ngen','compare'],required=True)
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
                results.append(dict(n=n,architecture=arch,returncode=code,directory=str(directory),
                                    log=str(directory/'driver.log'),summaries=[str(p) for p in directory.glob('*/summary.json')]))
                write_json(out/'probes.json',dict(complete=len(results)==6 and all(r['returncode']==0 for r in results),runs=results,
                    scope='Code generation and custom BU probe; whole-kernel matched measurements remain separate.'))
        return int(any(r['returncode'] for r in results))
    if a.stage=='field':
        if a.design is None:p.error('--design required')
        shutil.copyfile(a.design/'ntt.h',out/'ntt.h')
        source=out/'parameters.cpp';source.write_text(study.parameter_source((a.design/'ntt_test.cpp').read_text()))
        with (out/'build.log').open('w') as log:
            subprocess.run(['g++','-std=c++17','-O2','-I/home/opt/xilinx/Vitis_HLS/2023.2/include',str(source),'-o',str(out/'parameters')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        with (out/'parameters.log').open('w') as log:subprocess.run([str(out/'parameters')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        fields=[]
        from architecture_search import oracle
        for line in (out/'parameters.log').read_text().splitlines():
            if line.startswith('LLMNTT field '):
                n,q,root,limb=map(int,line.split()[2:]);w=dict(n=n,q=str(q),root=str(root),negacyclic=False)
                oracle.validate(w);fields.append(w);write_json(out/f'field-{limb}.json',w)
        if not fields:raise ValueError('no captured parameters')
        write_json(out/'field-capture.json',dict(schema='autontt-host-field-v1',fields=fields,autontt_revision=study.PIN,
            scope='Generated host parameters only; no AutoNTT kernel or timing qualification.',
            artifacts=artifact_manifest([source,out/'ntt.h',out/'parameters.log',a.design/'ntt_test.cpp'])))
        return 0
    if a.stage=='trace':
        if a.design is None or a.architecture is None:p.error('--design and --architecture required')
        d=out/'csim'
        if d.exists():raise ValueError('existing C-simulation directory')
        shutil.copytree(a.design,d)
        host=d/'ntt_test.cpp';host.write_text(study.instrument_host(host.read_text()))
        # The pinned generated Makefile omits transitive libraries needed by
        # the current TAPA C++ runtime. Link the unmodified generated kernel
        # and instrumented host with the dependency set checked by
        # check_autontt_hls_deps.sh.
        # The packaged runtime contains split-stack objects. Apply the same
        # compiler mode to the generated host so libgcc initializes their
        # stack allocator before TAPA starts its software tasks.
        link=['g++','-fsplit-stack','ntt_kernel.cpp','ntt_test.cpp','-o','ntt',
              '-I/home/opt/xilinx/Vitis_HLS/2023.2/include','-O2']
        tapa_home=os.environ.get('TAPA_HOME') or os.environ.get('RAPIDSTREAM_INSTALL_DIR')
        if tapa_home:
            libdir=next((p for p in (Path(tapa_home)/'usr/lib',Path(tapa_home)/'lib') if p.is_dir()),None)
            if libdir:link.extend([f'-L{libdir}',f'-Wl,-rpath,{libdir}'])
        link.extend(['-ltapa','-lfrt','-lglog','-lgflags','-lOpenCL',
                     '-lyaml-cpp','-ltinyxml2','-lthread','-lcontext','-pthread',
                     '-std=c++17','-DBU_BUF_FIFO_DEPTH=1024'])
        with (d/'build.log').open('w') as log:
            subprocess.run(link,cwd=d,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200)
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
