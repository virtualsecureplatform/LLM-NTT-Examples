#!/usr/bin/env python3
"""Budgeted FPGA mapping, calibrated acquisition, and routed qualification."""
import argparse
import csv
import fcntl
import json
import re
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from architecture_search import device, device_evaluate as backend, device_search as acquisition
from architecture_search.model import artifact_manifest,evidence_integrity,file_hash,write_json
from scripts.polynomial_study import reusable


def inventory(campaigns):
    rows={};sources=[];corpora={}
    for folder in campaigns:
        folder=folder.resolve()
        data=json.loads((folder/'results.json').read_text())
        manifest=json.loads((folder/'manifest.json').read_text())
        sources.append(dict(results=str(folder/'results.json'),results_sha256=file_hash(folder/'results.json'),
                            manifest_sha256=file_hash(folder/'manifest.json')))
        for name,sha in manifest['corpora'].items():
            if name in corpora and corpora[name]!=sha: raise ValueError('different corpora for '+name)
            corpora[name]=sha
        for row in data['points']:
            if not row.get('passed'):continue
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',row['name']):raise ValueError('unsafe point identifier')
            root=Path(row.get('evidence_root',folder))
            r={**row,'evidence_root':str(root),'rtl_path':str(root/row['name']/'SearchTop.sv')}
            if r['name'] in rows:
                old=rows[r['name']]
                if any(old[k]!=r[k] for k in ('workload','configuration','rtl_sha256','yosys_cells','memory_bits',
                                              'register_bits','multipliers','latency_cycles','initiation_interval_cycles','max_abs_error')):
                    raise ValueError('conflicting qualified point '+r['name'])
            else: rows[r['name']]=r
    if not rows:raise ValueError('no qualified products')
    contracts={}
    for r in rows.values():
        w=r['workload_name']
        if w in contracts and contracts[w]!=r['workload']:raise ValueError('workload name has different contracts')
        contracts[w]=r['workload']
    return list(rows.values()),sources


def state_summary(state,rows,target,error_limit):
    byname={r['name']:r for r in rows}
    feasible=[name for name,e in state['routed'].items() if device.feasible(byname[name],e,target,error_limit)]
    frontiers={}
    for workload in sorted({r['workload_name'] for r in rows}):
        names=[name for name in feasible if byname[name]['workload_name']==workload]
        def objectives(name):
            r=byname[name];m=state['routed'][name]['metrics'];p=device.performance(r,target)
            return [r['max_abs_error'],*(m[k] for k in device.RESOURCES),p['kernel_latency_seconds'],-p['modeled_products_per_second']]
        frontiers[workload]=[name for name in names if not any(all(a<=b for a,b in zip(objectives(other),objectives(name)))
                              and any(a<b for a,b in zip(objectives(other),objectives(name))) for other in names)]
    return feasible,frontiers


def save(out,state,rows,target,error_limit):
    byname={r['name']:r for r in rows}
    feasible,frontiers=state_summary(state,rows,target,error_limit)
    state['feasible']=feasible;state['frontiers']=frontiers
    state['heldout_validation']=acquisition.heldout_errors(rows,
        {n:state['mapped'][n] for n in state['calibration'] if n in state['mapped']},
        {n:state['mapped'][n] for n in state['heldout'] if n in state['mapped']})
    write_json(out/'results.json',state)
    fields=['name','workload','family','phase','mapped_passed','routed_passed','feasible',*device.RESOURCES,
            'setup_slack_ns','hold_slack_ns','pulse_slack_ns','error_bound','modeled_products_per_second','bytes_per_product']
    with (out/'points.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fields,extrasaction='ignore',lineterminator='\n');writer.writeheader()
        for name,mapped in state['mapped'].items():
            r=byname[name];routed=state['routed'].get(name,{})
            writer.writerow(dict(name=name,workload=r['workload_name'],family=acquisition.family(r),
                phase='calibration' if name in state['calibration'] else 'heldout' if name in state['heldout'] else 'search',
                mapped_passed=mapped['passed'],routed_passed=routed.get('passed',False),feasible=name in feasible,
                **routed.get('metrics',mapped.get('metrics',{})),error_bound=r['max_abs_error'],**device.performance(r,target)))
    lines=['# Device-aware polynomial product search','',f"Status: {state['status']}. Policy: {state['policy']}.",'',
           f"Mapped attempts: {len(state['mapped'])}; routed attempts: {len(state['routed'])}; feasible designs: {len(feasible)}.",'',
           ('Registered on-chip kernel harness with a routed BUFG clock. Resources include the harness; kernel hierarchy is reported separately. '
            if target.get('implementation_context','').startswith('registered-harness-') else 'Out-of-context kernel implementation. ')+
           'Bandwidth-limited rates are modeled, not board measurements. All exposed data ports are constrained; '
           'mapped resource success alone does not establish timing feasibility.','',
           '| Workload | Routed feasible designs | Best modeled products/s |','| --- | ---: | ---: |']
    for workload in frontiers:
        names=[n for n in feasible if byname[n]['workload_name']==workload]
        rate=max((device.performance(byname[n],target)['modeled_products_per_second'] for n in names),default=None)
        lines.append(f'| {workload} | {len(names)} | {rate if rate is not None else "no feasible design found within budget"} |')
    lines+=['','See [points.csv](points.csv) for measured resources, timing, and modeled rates; '
            '[results.json](results.json) for sealed evidence, acquisition history, held-out prediction errors, and Pareto memberships.','']
    (out/'summary.md').write_text('\n'.join(lines))


def recover_active(out,state,byname,target,tool):
    """Adopt a sealed finished stage, or charge an interrupted attempt once."""
    active=state.get('active')
    if active is None:return
    name,stage=active['name'],active['stage'];folder=out/name/stage
    tcl=str(folder/'run.tcl').encode()
    for cmdline in Path('/proc').glob('[0-9]*/cmdline'):
        try:arguments=cmdline.read_bytes().split(b'\0')
        except OSError:continue
        if tcl in arguments:raise ValueError('the interrupted trial still has a live Vivado process')
    evidence_file=folder/'evidence.json'
    if evidence_file.exists():
        e=json.loads(evidence_file.read_text())
        if e.get('target')!=target or e.get('tool')!=tool or e.get('rtl_sha256')!=byname[name]['rtl_sha256'] or evidence_integrity(e)!='verified':
            raise ValueError('interrupted trial has invalid sealed evidence')
    else:
        folder.mkdir(parents=True,exist_ok=True)
        log=folder/'interrupted.log';log.write_text('Interrupted attempt: completion was not sealed; charged to budget.\n')
        e=dict(stage=stage,target=target,tool=tool,rtl_sha256=byname[name]['rtl_sha256'],
               checkpoint=str(folder/'design.dcp'),passed=False,metrics={},reason='interrupted')
        e['integrity']=dict(version=1,inputs_unchanged=True,
            inputs=artifact_manifest([byname[name]['rtl_path']]),outputs=artifact_manifest([log]),
            measurement={k:e[k] for k in ('stage','target','tool','rtl_sha256','checkpoint','passed','metrics')})
        write_json(evidence_file,e)
    state[stage][name]=e;state['active']=None
    state['elapsed_seconds']+=max(0,time.time()-active.get('started_at',time.time()))
    state['history'].append(dict(name=name,stage=stage,phase=active['phase'],passed=e['passed'],
        recovered=True,evaluation_count=len(state['mapped'])+len(state['routed']),elapsed_seconds=state['elapsed_seconds']))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,action='append',required=True)
    p.add_argument('--configuration-name',action='append',help='Restrict evaluation to named qualified points')
    p.add_argument('--target',type=Path,default=ROOT/'studies/u280-device.json')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--policy',choices=['enumerate','random','model'],default='model')
    p.add_argument('--seed',type=int,default=1)
    p.add_argument('--max-trials',type=int,default=24,help='Total mapped attempts, including calibration and held-out cases')
    p.add_argument('--route-budget',type=int,default=6)
    p.add_argument('--max-route-budget',type=int,default=12)
    p.add_argument('--error-limit',type=int,default=0)
    p.add_argument('--timeout',type=int,default=3600)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--vivado',type=Path,default=Path('/home/opt/xilinx/Vivado/2023.2/bin/vivado'))
    p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    lock=None
    try:
        target=device.load_target(args.target)
        if args.error_limit<0 or args.max_trials<1 or args.timeout<1 or not 1<=args.threads<=32 or not 0<=args.route_budget<=args.max_route_budget:
            raise ValueError('invalid budget, timeout, error limit, or thread count')
        rows,sources=inventory(args.campaign)
        if args.configuration_name:
            wanted=set(args.configuration_name)
            if wanted-{r['name'] for r in rows}:raise ValueError('unknown qualified configuration name')
            rows=[r for r in rows if r['name'] in wanted]
        byname={r['name']:r for r in rows}
        calibration,heldout=acquisition.calibration_split(rows)
        if args.max_trials<len(calibration)+len(heldout):raise ValueError('max-trials must cover calibration and held-out cases')
        plan=dict(candidates=len(rows),calibration=calibration,heldout=heldout,
                  mapped_budget=args.max_trials,initial_route_budget=args.route_budget,max_route_budget=args.max_route_budget)
        if args.dry_run: print(json.dumps(plan,indent=2));return 0
        out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
        lock=(out/'.lock').open('w')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('campaign is already running')
        tool=backend.tool_identity(args.vivado,out)
        if tool['version']!=target['vivado_version']:raise ValueError('wrong Vivado version')
        manifest=dict(schema='device-polynomial-manifest-v1',target=target,tool=tool,sources=sources,
                      policy=args.policy,seed=args.seed,max_trials=args.max_trials,route_budget=args.route_budget,
                      max_route_budget=args.max_route_budget,error_limit=args.error_limit,threads=args.threads,
                      plan=plan,selected=args.configuration_name,code={str(path.relative_to(ROOT)):file_hash(path) for path in
                        [Path(__file__),ROOT/'architecture_search/device.py',ROOT/'architecture_search/device_search.py',
                         ROOT/'architecture_search/device_evaluate.py',ROOT/'architecture_search/timing_harness.py',
                         ROOT/'architecture_search/model.py',ROOT/'scripts/polynomial_study.py']})
        mp=out/'manifest.json'
        if args.resume:
            if not mp.is_file() or json.loads(mp.read_text())!=manifest:raise ValueError('resume manifest differs')
            state=json.loads((out/'results.json').read_text())
            for stage in ('mapped','routed'):
                for name,e in state[stage].items():
                    if e.get('target')!=target or e.get('tool')!=tool or e.get('rtl_sha256')!=byname[name]['rtl_sha256'] or evidence_integrity(e)!='verified':
                        raise ValueError('invalid cached evidence for '+name)
        else:
            if mp.exists():raise ValueError('campaign exists; use --resume')
            write_json(mp,manifest)
            state=dict(schema='device-polynomial-results-v1',status='running',policy=args.policy,seed=args.seed,
                       calibration=calibration,heldout=heldout,mapped={},routed={},history=[],active=None,elapsed_seconds=0)
        recover_active(out,state,byname,target,tool)
        began=time.monotonic();previous_elapsed=state['elapsed_seconds']
        def checkpoint():
            state['elapsed_seconds']=previous_elapsed+time.monotonic()-began
            save(out,state,rows,target,args.error_limit)
        def measure(row,stage,phase,prediction=None):
            name=row['name'];folder=out/name/stage
            if not reusable(row,Path(row['evidence_root']),row):raise ValueError('original qualification evidence changed for '+name)
            state['active']=dict(name=name,stage=stage,phase=phase,started_at=time.time());checkpoint()
            print(f'{stage}: {name} ({phase})',flush=True)
            e=backend.evaluate(row,row['rtl_path'],target,tool,args.vivado,folder,stage,
                               state['mapped'].get(name),args.timeout,args.threads)
            state[stage][name]=e;state['active']=None
            state['history'].append(dict(name=name,stage=stage,phase=phase,prediction=prediction,
                passed=e['passed'],evaluation_count=len(state['mapped'])+len(state['routed']),
                elapsed_seconds=previous_elapsed+time.monotonic()-began))
            checkpoint()
            state['history'][-1]['best_feasible_rates']={w:max((device.performance(byname[n],target)['modeled_products_per_second']
                for n in state['feasible'] if byname[n]['workload_name']==w),default=None) for w in state['frontiers']}
            checkpoint()
        state['status']='running';checkpoint()
        for phase,names in [('calibration',calibration),('heldout',heldout)]:
            for name in names:
                if name not in state['mapped']:measure(byname[name],'mapped',phase)
        while len(state['mapped'])<args.max_trials:
            remaining=[r for r in rows if r['name'] not in state['mapped'] and r['max_abs_error']<=args.error_limit]
            if not remaining:break
            observed=[(byname[n],e) for n,e in state['mapped'].items() if n not in heldout]
            row,prediction=acquisition.choose(remaining,observed,target,args.policy,args.seed,len(state['mapped']))
            measure(row,'mapped','search',prediction)
        workloads=sorted({r['workload_name'] for r in rows})
        while len(state['routed'])<args.max_route_budget:
            feasible,_=state_summary(state,rows,target,args.error_limit)
            if len(state['routed'])>=args.route_budget and all(any(byname[n]['workload_name']==w for n in feasible) for w in workloads):break
            options=[r for r in rows if r['name'] in state['mapped'] and r['name'] not in state['routed']
                     and state['mapped'][r['name']]['passed'] and device.resources_fit(state['mapped'][r['name']]['metrics'],target)
                     and r['max_abs_error']<=args.error_limit]
            if not options:break
            counts={w:sum(byname[n]['workload_name']==w for n in state['routed']) for w in workloads}
            def route_rank(r):
                slack=state['mapped'][r['name']]['metrics'].get('setup_slack_ns',-1e30)
                # A timing estimate ranks trials; only the routed checks establish feasibility.
                return (any(byname[n]['workload_name']==r['workload_name'] for n in feasible),
                        counts[r['workload_name']],max(0,-slack),
                        -device.performance(r,target)['modeled_products_per_second'],r['yosys_cells'],r['name'])
            options.sort(key=route_rank)
            measure(options[0],'routed','finalist')
        for name in state['feasible']:
            dest=out/'exports'/name;dest.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(byname[name]['rtl_path'],dest/'SearchTop.sv')
            route=out/name/'routed'
            shutil.copyfile(route/'constraints.xdc',dest/'constraints.xdc')
            if target.get('implementation_context','').startswith('registered-harness-'):
                shutil.copyfile(route/'TimingHarness.sv',dest/'TimingHarness.sv')
            write_json(dest/'manifest.json',dict(target=target,tool=tool,configuration=byname[name]['configuration'],
                workload=byname[name]['workload'],rtl_sha256=file_hash(dest/'SearchTop.sv'),
                constraints_sha256=file_hash(dest/'constraints.xdc'),evidence=str(route/'evidence.json'),
                evidence_sha256=file_hash(route/'evidence.json'),implementation_context=target.get('implementation_context','standalone'),
                harness_sha256=file_hash(dest/'TimingHarness.sv') if (dest/'TimingHarness.sv').exists() else None))
        state['status']='complete';checkpoint()
        print('Complete: '+str(len(state['feasible']))+' routed feasible designs.',flush=True)
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:p.error(str(error))
    finally:
        if lock is not None:lock.close()


if __name__=='__main__':raise SystemExit(main())
