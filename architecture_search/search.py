"""Reproducible, budgeted architecture experiments with independent correctness gates."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import shutil
import subprocess
import time
from . import adapters, oracle, hardware, policy, cost, constraints
from .evaluate import evaluate_generic, generic_simulator, parse_metrics
from .model import digest, file_hash, frontier, metric_number, run, source_identity, write_json

ROOT = Path(__file__).resolve().parents[1]


def tool_identity(command: list[str]) -> dict:
    path = shutil.which(command[0])
    if not path:
        return {'available': False}
    try:
        text = subprocess.check_output(command, stderr=subprocess.STDOUT, timeout=20).decode(errors='replace')
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        text = str(error)
    return {'path': str(Path(path).resolve()), 'version': text[:4096]}


def report(directory: Path, campaign: dict) -> dict:
    records = [json.loads(p.read_text()) for p in sorted((directory/'candidates').glob('*/record.json'))]
    target = campaign.get('target', {})
    transport=constraints.bandwidth_bound(campaign['workload'],campaign.get('bandwidth',{}))
    for record in records:
        for stage in ('synthesis','route'):
            e=record.get('evidence',{}).get(stage,{})
            metrics=e.get('metrics',{});rate=metrics.get('transforms_per_second')
            if metric_number(rate):
                metrics['bandwidth_capped_transforms_per_second']=min(rate,transport['upper_transforms_per_second']) if transport else rate
    frontiers = {}
    for stage, objectives in [('simulation', {'latency_cycles':'min','initiation_interval_cycles':'min'}),
                              ('synthesis', {'latency_ns':'min','transforms_per_second':'max','lut':'min','ff':'min','dsp':'min','bram':'min','uram':'min'}),
                              ('route', {'latency_ns':'min','transforms_per_second':'max','lut':'min','ff':'min','dsp':'min','bram':'min','uram':'min'})]:
        if campaign['workload']['kind']=='preset':
            objectives={**{k:v for k,v in objectives.items() if k not in ('latency_cycles','latency_ns','initiation_interval_cycles','transforms_per_second')}, ('transaction_cycles' if stage=='simulation' else 'transaction_ns'):'min'}
        minimums={}
        if stage!='simulation' and campaign['workload']['kind']=='generic':
            if transport or campaign.get('requirements'):
                objectives={('bandwidth_capped_transforms_per_second' if k=='transforms_per_second' else k):v for k,v in objectives.items()}
            required=campaign.get('requirements',{}).get('min_transforms_per_second')
            if required is not None:minimums={'bandwidth_capped_transforms_per_second':required}
        frontiers[stage] = frontier(records, objectives, stage, target, campaign.get('resource_limits', {}) if stage!='simulation' else {},minimums)
    result = {'schema':'ntt-search-report-v1', 'workload':campaign['workload'], 'frontiers':frontiers,
              'counts':{status:sum(r['status']==status for r in records) for status in sorted({r['status'] for r in records})},
              'candidates':records}
    write_json(directory/'report.json', result)
    lines = ['# Architecture search results', '', 'Frontiers are separated by evidence stage. Missing metrics are not zero.', '',
             '| Candidate | Status | Correct | Latency cycles | Frame interval cycles |', '| --- | --- | --- | --- | --- |']
    for r in records:
        m=r.get('evidence',{}).get('simulation',{}).get('metrics',{})
        lines.append(f"| {r['id'][:12]} | {r['status']} | {r.get('correct', False)} | {m.get('latency_cycles','unmeasured')} | {m.get('initiation_interval_cycles','unmeasured')} |")
    if campaign['workload']['kind']=='preset':
        lines[4]='| Candidate | Status | Correct | Transaction cycles | Frame interval cycles |'
        for index,r in enumerate(records,6):
            m=r.get('evidence',{}).get('simulation',{}).get('metrics',{})
            lines[index]=f"| {r['id'][:12]} | {r['status']} | {r.get('correct',False)} | {m.get('transaction_cycles','unmeasured')} | unmeasured |"
    for stage, ids in frontiers.items():
        lines += ['', f'{stage} frontier: '+(', '.join(i[:12] for i in ids) or 'unavailable')]
    lines += ['', '| Candidate | Configuration |', '| --- | --- |']
    for r in records:
        lines.append('| '+r['id'][:12]+' | '+', '.join(f'{k}={v}' for k,v in r['configuration'].items())+' |')
    for stage in ('synthesis','route'):
        measured=[r for r in records if stage in r.get('evidence',{})]
        if measured:
            lines += ['', f'{stage} evidence:', '', '| Candidate | Timing clean | LUT | FF | DSP | BRAM | URAM | WNS ns | Hold ns |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
            for r in measured:
                e=r['evidence'][stage];m=e.get('metrics',{})
                lines.append('| '+r['id'][:12]+' | '+str(e.get('timing_clean',False))+' | '+' | '.join(str(m.get(k,'unmeasured')) for k in ('lut','ff','dsp','bram','uram','wns_ns','hold_slack_ns'))+' |')
    (directory/'report.md').write_text('\n'.join(lines)+'\n')
    return result


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--ngen-root',type=Path,default=ROOT.parent/'NGen')
    parser.add_argument('--sgen-root',type=Path,default=ROOT.parent/'SGen')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--mode',choices=['plan','run','resume','report'],default='plan')
    parser.add_argument('--policy',choices=['enumerate','random','llm','cost'],default='enumerate')
    parser.add_argument('--cost-model',type=Path)
    parser.add_argument('--seed',type=int,default=1)
    parser.add_argument('--configuration-json',type=Path,help='evaluate exactly one configuration, which must belong to the declared legal space')
    args=parser.parse_args(argv)
    build_identity=None
    if args.mode in ('run','resume'):
        from .build_identity import verify
        build_identity=verify(args.ngen_root)
        if not build_identity['verified']:
            parser.error('NGen build verification failed: '+json.dumps(build_identity)+'; run sbt assembly')
    campaign=json.loads(args.campaign.read_text())
    campaign['target']={'part':'xcu280-fsvh2892-2L-e','tool_version':'2023.2','clock_period_ns':4.0,**campaign.get('target',{})}
    limits={'hours':12,'functional':64,'synthesis':12,'route':4,**campaign.get('budget',{})}
    if any(not isinstance(limits[k],(int,float)) or isinstance(limits[k],bool) or limits[k]<0 for k in limits):
        parser.error('budgets must be nonnegative numbers')
    if any(not isinstance(limits[k],int) for k in ('functional','synthesis','route')):
        parser.error('candidate budgets must be integers')
    if campaign['target']['clock_period_ns']<=0:parser.error('clock period must be positive')
    workload=campaign['workload']
    if workload['kind']=='generic':
        oracle.validate(workload)
    else:
        task_config=json.loads((ROOT/'tasks'/f"{workload['task']}.json").read_text())
        campaign['target'].setdefault('clock_port',task_config.get('ports',{}).get('clock','clock'))
    evaluation_options=campaign.get('evaluation',{})
    if not isinstance(evaluation_options,dict) or set(evaluation_options)-{'simulator','timeout_seconds'}:
        parser.error('evaluation supports only simulator and timeout_seconds')
    evaluation_timeout=evaluation_options.get('timeout_seconds',1200)
    if not metric_number(evaluation_timeout) or evaluation_timeout<=0:parser.error('evaluation timeout must be finite and positive')
    if workload['kind']=='generic':
        try:generic_simulator(workload,evaluation_options.get('simulator','auto'))
        except ValueError as error:parser.error(str(error))
    elif 'simulator' in evaluation_options:parser.error('simulator selection is only supported for generic workloads')
    ngen=args.ngen_root.resolve(); directory=args.output_dir.resolve()
    configurations=adapters.candidates(workload,ngen,campaign.get('space'))
    if args.configuration_json is not None:
        selected=json.loads(args.configuration_json.read_text())
        if selected not in configurations:parser.error('selected configuration is outside the legal campaign space')
        configurations=[selected]
    try:
        bounds={digest(c):constraints.analyze(workload,c,campaign['target'],campaign.get('bandwidth'),campaign.get('requirements')) for c in configurations}
        storage_bounds={digest(c):constraints.storage_bound(workload,c,campaign['target'],campaign.get('resource_limits')) for c in configurations}
    except ValueError as error:parser.error(str(error))
    if args.policy=='random':
        random.Random(args.seed).shuffle(configurations)
    fitted=None
    if args.policy=='cost':
        if args.cost_model is None:parser.error('--policy cost requires --cost-model')
        fitted=json.loads(args.cost_model.read_text())
        if fitted['workload']!=workload or fitted['target']!=campaign.get('target',{}):parser.error('cost model workload/target mismatch')
        predictions=[(cost.predict(fitted['samples'],c,'lut','structural' if fitted.get('method')=='structural' else 'nearest'),c) for c in configurations]
        # Reserve every fourth proposal for seeded exploration, even with a fitted model.
        ranked=[c for estimate,c in sorted(predictions,key=lambda pair:pair[0].get('estimate',float('inf')))]
        exploration=list(configurations);random.Random(args.seed).shuffle(exploration)
        configurations=[]
        while ranked or exploration:
            pool=exploration if len(configurations)%4==3 and exploration else ranked or exploration
            candidate=pool.pop(0)
            if candidate not in configurations:configurations.append(candidate)
            ranked=[c for c in ranked if c!=candidate];exploration=[c for c in exploration if c!=candidate]
    stages=campaign.get('stages',['simulation'])
    if any(s not in ('simulation','synthesis','route') for s in stages):
        parser.error('unknown evaluation stage')
    plan={'schema':'ntt-search-plan-v1','campaign':campaign,'policy':args.policy,'seed':args.seed,'configurations':configurations,'cost_model':fitted,'throughput_bounds':bounds,'storage_bounds':storage_bounds}
    if args.mode=='plan':
        print(json.dumps(plan,indent=2));return 0
    if args.mode=='report':
        saved=json.loads((directory/'manifest.json').read_text())
        if saved['campaign']!=campaign:
            parser.error('campaign differs from saved run')
        print(json.dumps(report(directory,campaign)['frontiers'],indent=2));return 0
    if not (ngen/'ngen.bat').is_file():
        parser.error('build NGen with sbt assembly before running a campaign')
    identity={'ngen_build':build_identity,'search':source_identity(ROOT),'ngen':source_identity(ngen),'ngen_binary':file_hash(ngen/'ngen.bat'),
              'tools':{'iverilog':tool_identity(['iverilog','-V']),'vvp':tool_identity(['vvp','-V']),
                       'verilator':tool_identity(['verilator','--version']),'cxx':tool_identity(['clang++','--version']),
                       'cmake':tool_identity(['cmake3' if shutil.which('cmake3') else 'cmake','--version'])}}
    if any(s in stages for s in ('synthesis','route')):
        target=campaign.get('target',{})
        identity['tools']['vivado']=tool_identity([target.get('vivado',f"/home/opt/xilinx/Vivado/{target.get('tool_version','2023.2')}/bin/vivado"),'-version'])
    uses_sgen=any(c['generator'] in ('ngen-sgen','ngen-sgen-linear') for c in configurations)
    if uses_sgen:
        identity['sgen']=source_identity(args.sgen_root.resolve())
        identity['sgen_binary']=file_hash(args.sgen_root/'sgen.bat')
    manifest={**plan,'identity':identity}
    manifest_path=directory/'manifest.json'
    if args.mode=='resume':
        if not manifest_path.exists() or json.loads(manifest_path.read_text())!=manifest:
            parser.error('resume requires identical source, tools, workload, policy, and constraints')
    elif directory.exists() and any(directory.iterdir()):
        parser.error('output directory is not empty; use resume or a new directory')
    write_json(manifest_path,manifest)
    executable=directory/'generator/ngen.bat'
    executable.parent.mkdir(parents=True,exist_ok=True)
    if not executable.exists():
        shutil.copyfile(ngen/'ngen.bat',executable)
    if file_hash(executable)!=identity['ngen_binary']:
        parser.error('generator snapshot differs from recorded binary')
    sgen_executable=None
    if uses_sgen:
        sgen_executable=directory/'generator/sgen.bat'
        if not sgen_executable.exists():shutil.copyfile(args.sgen_root/'sgen.bat',sgen_executable)
        if file_hash(sgen_executable)!=identity['sgen_binary']:parser.error('SGen snapshot hash mismatch')
    state_path=directory/'state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'seconds':0,'functional':0,'synthesis':0,'route':0}
    start=time.monotonic(); previous=state['seconds']
    def remaining():
        return max(0,limits['hours']*3600-previous-(time.monotonic()-start))
    def checkpoint():
        state['seconds']=previous+time.monotonic()-start
        write_json(state_path,state)
    if args.policy=='llm':
        order_path=directory/'selection.json'
        if order_path.exists():
            configurations=json.loads(order_path.read_text())
            if sorted(map(digest,configurations))!=sorted(map(digest,plan['configurations'])):
                parser.error('saved selection differs from legal candidate set')
        else:
            try:
                configurations=policy.rank(configurations,workload,{**campaign.get('llm',{}),'target':campaign.get('target',{}),'resource_limits':campaign.get('resource_limits',{}),'requirements':campaign.get('requirements',{}),'bandwidth':campaign.get('bandwidth',{}),'objectives':campaign.get('objectives',{}),'evaluations_remaining':max(0,limits['functional']-state['functional'])},directory,min(campaign.get('llm',{}).get('timeout_seconds',180),remaining()))
            except (ValueError,KeyError,OSError) as error:
                write_json(directory/'llm-error.json',{'error':str(error),'fallback':'seeded random'})
                random.Random(args.seed).shuffle(configurations)
            write_json(order_path,configurations)
            checkpoint()
    for config in configurations:
        key=digest({'manifest':manifest,'config':config})
        work=directory/'candidates'/key; path=work/'record.json'
        if path.exists() and json.loads(path.read_text()).get('status') not in ('running',):
            continue
        if bounds[digest(config)]['pruned'] or storage_bounds[digest(config)]['pruned']:
            write_json(path,{'schema':'ntt-search-candidate-v1','id':key,'configuration':config,'status':'pruned','correct':False,'mode':'bound','evidence':{},'throughput_bound':bounds[digest(config)],'storage_bound':storage_bounds[digest(config)]})
            continue
        if remaining()<=0 or state['functional']>=limits['functional']:
            break
        record={'schema':'ntt-search-candidate-v1','id':key,'configuration':config,'status':'running','correct':False,'mode':'functional','evidence':{}}
        write_json(path,record)
        state['functional']+=1;checkpoint()
        try:
            generation,rtl=adapters.generate(workload,config,ngen,work/'generated',min(600,remaining()),executable,sgen_executable)
            record['generation']=generation
            if generation['returncode']!=0:
                record['status']='generation_failed'
            else:
                record['rtl_path']=str(rtl)
                record['rtl_hash']=file_hash(rtl)
                metadata=rtl.with_suffix('.json')
                record['declared']=json.loads(metadata.read_text()) if metadata.exists() else {}
                # Paths in metadata are not hardware identities. Only exact RTL matches are reused.
                duplicate=None
                for other in (directory/'candidates').glob('*/record.json'):
                    old=json.loads(other.read_text())
                    if old.get('rtl_hash')==record['rtl_hash'] and old.get('status')=='complete':
                        duplicate=old;break
                if duplicate:
                    record.update(status='duplicate',duplicate_of=duplicate['id'])
                else:
                    evaluation_dir=work/'evaluation'
                    if workload['kind']=='generic':
                        evaluation=evaluate_generic(workload,config,rtl,evaluation_dir,min(evaluation_timeout,remaining()),simulator=evaluation_options.get('simulator','auto'))
                    else:
                        task=ROOT/'tasks'/f"{workload['task']}.json"
                        process=run(['bash',str(ROOT/'scripts/evaluate_candidate.sh'),'--task',str(task),'--verilog-file',str(rtl),
                                     '--build-dir',str(evaluation_dir)],ROOT,work/'evaluation.log',min(evaluation_timeout,remaining()))
                        result_path=evaluation_dir/'results.json'
                        raw=json.loads(result_path.read_text()) if result_path.exists() else {}
                        evaluation={'correct':process['returncode']==0 and raw.get('correct') is True and raw.get('mode')=='verilator_test',
                                    'metrics':raw.get('metrics',{}),'process':process}
                        # Legacy test metrics expose transaction time, not sustained throughput.
                        totals=[]
                        for name,value in evaluation['metrics'].items():
                            if name.endswith('_input_cycles'):
                                prefix=name[:-len('_input_cycles')]
                                parts=[evaluation['metrics'].get(prefix+suffix) for suffix in ('_input_cycles','_max_wait_cycles','_output_cycles')]
                                if all(isinstance(p,(int,float)) for p in parts):
                                    totals.append(sum(parts))
                        if totals:
                            evaluation['metrics']['transaction_cycles']=max(totals)
                    record['correct']=evaluation['correct']
                    record['evaluation']=evaluation
                    record['evidence']['simulation']={'passed':evaluation['correct'],'target':campaign.get('target',{}),'metrics':evaluation['metrics']}
                    record['status']='complete' if evaluation['correct'] else 'incorrect'

        except (ValueError,KeyError,OSError) as error:
            record.update(status='error',error=str(error))
        write_json(path,record);checkpoint()
        print(f"{key[:12]} {record['status']}",flush=True)
    # Complete cheap functional checks before spending implementation budgets.
    records=[json.loads(p.read_text()) for p in (directory/'candidates').glob('*/record.json')]
    qualified=[r for r in records if r.get('correct') and r.get('status')!='duplicate']
    # Sweep distinct hardware sizes to retain area/throughput diversity in the shortlist.
    qualified.sort(key=lambda r:(r['configuration'].get('pe',1)*r['configuration'].get('stage_groups',1),r['id']))
    for stage in ('synthesis','route'):
        if stage not in stages:continue
        if stage=='route':
            # Prefer synthesis timing closure, then closest misses; routing may improve setup.
            qualified.sort(key=lambda r:(not r.get('evidence',{}).get('synthesis',{}).get('timing_clean',False),
                -r.get('evidence',{}).get('synthesis',{}).get('metrics',{}).get('wns_ns',-1e9)))
        for record in qualified:
            if stage in record['evidence']:continue
            if remaining()<=0 or state[stage]>=limits[stage]:break
            work=directory/'candidates'/record['id'];path=work/'record.json'
            rtl=Path(record['rtl_path'])
            extras=[]
            if workload['kind']=='preset':
                extras=[ROOT/p for p in task_config.get('verilog',{}).get('extra_sources',[])]
            top='SearchTop' if workload['kind']=='generic' else json.loads((ROOT/'tasks'/f"{workload['task']}.json").read_text())['top_module']
            state[stage]+=1;checkpoint()
            try:
                record['evidence'][stage]=hardware.evaluate(rtl,top,campaign.get('target',{}),record['evaluation']['metrics'],work/stage,stage,min(5400 if stage=='synthesis' else 10800,remaining()),extra_sources=extras)
            except (ValueError,KeyError,OSError) as error:
                record['evidence'][stage]={'passed':False,'error':str(error)}
            record['status']='complete' if all(e.get('passed') for e in record['evidence'].values()) else 'hardware_failed'
            write_json(path,record);checkpoint()
            print(f"{record['id'][:12]} {stage}: {'passed' if record['evidence'][stage]['passed'] else 'failed'}",flush=True)
    checkpoint()
    result=report(directory,campaign)
    print(f"Report: {directory/'report.md'}",flush=True)
    if campaign.get('requirements') and any(s in stages for s in ('synthesis','route')):
        return 0 if result['frontiers']['route' if 'route' in stages else 'synthesis'] else 1
    return 0 if any(r.get('correct') and all(r.get('evidence',{}).get(stage,{}).get('passed') for stage in stages) for r in result['candidates']) else 1
