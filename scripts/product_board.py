#!/usr/bin/env python3
"""Select qualified N=64 products, package/link common board wrappers, and measure."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import products,product_backend,release
from architecture_search.model import file_hash,write_json,artifact_manifest
ROOT=Path(__file__).resolve().parents[1]
PLATFORM=Path('/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm')
VITIS=Path('/home/opt/xilinx/Vitis/2023.2/bin/v++')
VIVADO=Path('/home/opt/xilinx/Vivado/2023.2/bin/vivado')


def select(report):
    w=report['workload']
    if w!=products.workload(64):raise ValueError('board runner requires the frozen version-1 N=64 workload')
    pairs=[]
    for period in (8,16):
        chosen={}
        for gen in ('ngen','sgen'):
            eligible=[]
            for r in report['candidates']:
                e=r.get('evidence',{}).get('route',{});target=e.get('target',{})
                if r['configuration']['generator']!=gen or target.get('clock_period_ns')!=period:continue
                if target.get('part')!=release.TARGET['part'] or target.get('tool_version')!='2023.2':continue
                if not release._routed(r,target):continue
                if not product_backend.qualification_valid(w,r['declared'],Path(r['rtl_path'])):continue
                eligible.append(r)
            if eligible:chosen[gen]=min(eligible,key=lambda r:(-r['evidence']['route']['metrics']['products_per_second'],r['id']))
        if len(chosen)==2:pairs.append((period,chosen))
    if not pairs:raise ValueError('no verified qualified N=64 NTT/FFT pair at a common clock')
    return pairs[0]


def run(command,cwd,log,timeout):
    with (cwd/log).open('w') as stream:
        result=subprocess.run([str(x) for x in command],cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    if result.returncode:raise RuntimeError(f'command failed; see {cwd/log}')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--stage',choices=['select','build','run'],required=True)
    a=p.parse_args(argv);out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    report=json.loads(a.report.read_text());period,chosen=select(report)
    selection=dict(schema='product-board-selection-v1',report_sha256=file_hash(a.report),clock_period_ns=period,
                   candidates={g:dict(id=r['id'],rtl_sha256=file_hash(Path(r['rtl_path']))) for g,r in chosen.items()},
                   wrapper=artifact_manifest(list((ROOT/'board').glob('*'))))
    path=out/'selection.json'
    if path.exists() and json.loads(path.read_text())!=selection:raise ValueError('board selection or wrapper changed; use a new output directory')
    write_json(path,selection)
    if a.stage=='select':return 0
    mhz=1000/period
    for gen,r in chosen.items():
        d=out/gen;d.mkdir(exist_ok=True)
        if a.stage=='build':
            if (d/'ProductStream.xo').exists():raise ValueError('existing build; use a fresh output directory')
            shutil.copyfile(r['rtl_path'],d/'SearchTop.sv')
            for name in ('product_stream.sv','package_product.tcl','product_movers.cpp'):shutil.copyfile(ROOT/'board'/name,d/name)
            run([VIVADO,'-mode','batch','-source','package_product.tcl','-tclargs',release.TARGET['part']],d,'package.log',1800)
            for kernel in ('product_source','product_sink'):
                run([VITIS,'-c','-t','hw','--platform',PLATFORM,'--hls.clock',f'{int(mhz*1e6)}:{kernel}',
                     '-k',kernel,'product_movers.cpp','-o',kernel+'.xo'],d,kernel+'.log',3600)
            (d/'connectivity.cfg').write_text('[connectivity]\nnk=ProductStream:1:product\nnk=product_source:1:source\nnk=product_sink:1:sink\n'
                'stream_connect=source.output:product.s_axis\nstream_connect=product.m_axis:sink.input\n'
                'sp=source.a:HBM[0]\nsp=source.b:HBM[1]\nsp=sink.output:HBM[2]\n[clock]\n'
                f'freqHz={int(mhz*1e6)}:product,source,sink\n')
            run([VITIS,'-l','-t','hw','--platform',PLATFORM,'--config','connectivity.cfg',
                 'ProductStream.xo','product_source.xo','product_sink.xo','-o','product.xclbin'],d,'link.log',86400)
            projects=list((d/'_x/link/vivado/vpl/prj').glob('*.xpr'))
            if len(projects)!=1:raise ValueError('cannot identify linked Vivado project')
            run([VIVADO,'-mode','batch','-source',ROOT/'board/check_link.tcl','-tclargs',projects[0],period],d,'linked-check.log',1800)
            write_json(d/'build.json',dict(passed=True,artifacts=artifact_manifest([d/'product.xclbin',d/'link.log',d/'connectivity.cfg',d/'linked_metrics.json',d/'linked_timing.rpt',d/'linked_utilization.rpt'])))
        else:
            build=json.loads((d/'build.json').read_text())
            if not build['passed'] or artifact_manifest(build['artifacts']['files'],build['artifacts']['directories'])!=build['artifacts']:
                raise ValueError('board build artifacts changed')
            run(['g++','-std=c++17','-O2','-I/opt/xilinx/xrt/include',ROOT/'board/product_host.cpp',
                 '-L/opt/xilinx/xrt/lib','-Wl,-rpath,/opt/xilinx/xrt/lib','-lxrt_coreutil','-o','host'],d,'host-build.log',120)
            run(['./host','product.xclbin','measurements.json',products.output_width(report['workload']),mhz],d,'host.log',21600)
            measured=json.loads((d/'measurements.json').read_text())
            if not measured.get('passed') or len(measured['trials'])!=48:raise ValueError('incomplete board measurement')
            write_json(d/'evidence.json',dict(passed=True,candidate=r['id'],selection=selection,
                      artifacts=artifact_manifest([d/'product.xclbin',d/'measurements.json',d/'host.log',d/'host'])))
    return 0

if __name__=='__main__':raise SystemExit(main())
