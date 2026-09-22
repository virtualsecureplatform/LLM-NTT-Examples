#!/usr/bin/env python3
"""Build, verify and measure the pinned NGen/SGen product DSE release."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.paths import ROOT,NGEN,SGEN,require_checkout
from architecture_search import release
from architecture_search.build_identity import verify
from architecture_search.model import run,write_json
from architecture_search.search import main as search_main,report as search_report,tool_identity


def check(hardware=False):
    for root,name in ((NGEN,'NGen'),(SGEN,'SGen')):require_checkout(root,name)
    commands={'java':['java','-version'],'sbt':['sbt','--script-version'],
              'python3':['python3','--version'],'iverilog':['iverilog','-V'],
              'vvp':['vvp','-V'],'verilator':['verilator','--version']}
    tools={name:tool_identity(command) for name,command in commands.items()}
    # Native preset requirements are reported separately; product campaigns do
    # not use TFHEpp or Clang. Full regression reports retain any skipped tests.
    tools['preset_cxx']=tool_identity(['clang++','--version'])
    tools['preset_cmake']=tool_identity(['cmake3' if shutil.which('cmake3') else 'cmake','--version'])
    if hardware:tools['vivado']=tool_identity(['/home/opt/xilinx/Vivado/2023.2/bin/vivado','-version'])
    missing=[name for name,t in tools.items() if not name.startswith('preset_') and not t.get('available',bool(t.get('path')))]
    result=dict(passed=not missing,tools=tools,missing=missing,
                action='Install missing tools or set PATH; generators: git submodule update --init --recursive')
    print(json.dumps(result,indent=2),flush=True)
    return result


def build(out):
    preflight=check()
    write_json(out/'tools.json',preflight)
    if not preflight['passed']:raise ValueError('build prerequisites are missing')
    for name,root,tests in [('ngen',NGEN,'test'),('sgen',SGEN,'regular:test')]:
        result=run(['sbt',tests,'assembly'],root,out/f'{name}-build.log',3600)
        if result['returncode'] or not verify(root,generator=name)['verified']:
            raise ValueError(f'{name} build failed; see {out}/{name}-build.log')
    # Legacy behavioral-generator tests consume baseline Chisel RTL, which is
    # deliberately ignored by Git and must also exist in a fresh checkout.
    baseline=run(['bash','scripts/gen_verilog.sh'],ROOT,out/'legacy-rtl-build.log',1800)
    if baseline['returncode']:raise ValueError(f'legacy RTL generation failed; see {out}/legacy-rtl-build.log')
    result=run([sys.executable,'-m','unittest','discover','-s','tests/python'],ROOT,out/'python-tests.log',1800)
    if result['returncode'] or 'skipped=' in (out/'python-tests.log').read_text():
        raise ValueError(f'framework regression failed or skipped required checks; see {out}/python-tests.log')
    return {'passed':True,'ngen':verify(NGEN),'sgen':verify(SGEN,generator='sgen'),'legacy_rtl':baseline,'regression':result}


def execute_campaign(out,name,campaign,resume):
    path=out/'campaigns'/f'{name}.json';path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and json.loads(path.read_text())!=campaign:raise ValueError('saved release campaign differs: '+name)
    write_json(path,campaign)
    directory=out/name
    mode='resume' if resume and (directory/'manifest.json').exists() else 'run'
    code=search_main(['--campaign',str(path),'--output-dir',str(directory),'--mode',mode])
    data=json.loads((directory/'report.json').read_text()) if (directory/'report.json').exists() else {}
    acceptance=release.accept(data,campaign)
    return dict(passed=acceptance['passed'],exit_code=code,acceptance=acceptance,report=str(directory/'report.json'),campaign=str(path))


def summarize(out):
    results={}
    for path in sorted((out/'campaigns').glob('*.json')):
        name=path.stem;directory=out/name;campaign=json.loads(path.read_text())
        if not (directory/'manifest.json').exists():results[name]={'passed':False,'reason':'not started'};continue
        data=search_report(directory,campaign)
        results[name]=release.accept(data,campaign)
    required=['smoke',*[f'matrix-{n}' for n in (8,16,32,64,256)]]
    complete=all(results.get(n,{}).get('passed') for n in required) and any(v['passed'] for k,v in results.items() if k.startswith('hardware-'))
    summary=dict(schema='product-dse-release-v1',complete=complete,campaigns=results,
                 limitation='Routed fabric product measurements; no board or AutoNTT superiority claim.')
    write_json(out/'release-report.json',summary)
    lines=['# Product DSE release','',f'Complete: {complete}','','| Campaign | Passed |','| --- | --- |']
    lines += [f"| {name} | {result['passed']} |" for name,result in results.items()]
    lines+=['','See each campaign report for qualification, failures, measurements and provenance.',summary['limitation']]
    (out/'release-report.md').write_text('\n'.join(lines)+'\n')
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['check','build','smoke','matrix','hardware','report','all'],required=True)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/dse-v1')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args(argv);out=args.output_dir.resolve()
    # Repository-local installations are opt-in through PATH, never inferred.
    try:
        if args.stage=='report':
            summary=summarize(out);print(json.dumps(summary,indent=2));return 0 if summary['complete'] else 1
        if args.stage in ('check','all'):
            result=check(args.stage=='all')
            if not result['passed']:return 1
            if args.stage=='check':return 0
        out.mkdir(parents=True,exist_ok=True)
        if args.stage in ('build','all'):write_json(out/'build.json',build(out))
        if args.stage in ('smoke','all'):
            result=execute_campaign(out,'smoke',release.campaign(),args.resume)
            if not result['passed']:summarize(out);return 1
        if args.stage in ('matrix','all'):
            for n in (8,16,32,64,256):
                result=execute_campaign(out,f'matrix-{n}',release.campaign(n,matrix=True),args.resume)
                if not result['passed']:summarize(out);return 1
        if args.stage in ('hardware','all'):
            if not check(True)['passed']:return 1
            qualified=False
            for period in (4,8):
                result=execute_campaign(out,f'hardware-{period}ns',release.campaign(hardware=True,period=period),args.resume)
                if result['passed']:qualified=True;break
            if not qualified:summarize(out);return 1
        summary=summarize(out)
        if args.stage=='all':return 0 if summary['complete'] else 1
        return 0
    except (ValueError,OSError,KeyError) as error:
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
