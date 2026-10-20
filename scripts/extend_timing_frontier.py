#!/usr/bin/env python3
"""Extend the exact N512 full×ternary Pareto set under routed 250 MHz timing."""
import argparse
import csv
import fcntl
import json
from pathlib import Path
import re
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from architecture_search import device,device_evaluate as backend,timing_harness
from architecture_search.model import artifact_manifest,evidence_integrity,file_hash,write_json
from scripts.device_polynomial_study import inventory
from scripts.find_timing_met import verify_clock
from scripts.polynomial_study import reusable


def same_context(actual,target):
    return {k:v for k,v in actual.items() if k!='implementation_directive'}=={k:v for k,v in target.items() if k!='implementation_directive'}


def endpoint_counts(report):
    counts={k:int(v) for k,v in re.findall(r'^(Setup|Hold|PW)\s*:\s*(\d+)\s+Failing Endpoints',report,re.M)}
    return counts if set(counts)=={'Setup','Hold','PW'} else None


def nondominated(points):
    """Eight measured objectives; equal objective vectors both remain eligible."""
    def vector(p):return [p['error_bound'],*(p[k] for k in device.RESOURCES),p['latency_cycles'],-p['modeled_products_per_second']]
    return [p['name'] for p in points if not any(
        all(a<=b for a,b in zip(vector(q),vector(p))) and any(a<b for a,b in zip(vector(q),vector(p)))
        for q in points if q['name']!=p['name'])]


def rows_for_frontier(campaigns):
    rows,sources=inventory(campaigns)
    selected=[]
    for r in rows:
        c=r['configuration']
        if r['workload_name']!='full-ternary' or r['workload']['n']!=512:continue
        if any(c.get(k)!=v for k,v in dict(generator='ngen',backend='streamed',reduction='montgomery',radix=2,stage_groups=1).items()):continue
        if c.get('product_profile')=='registered' and c['lanes'] in (2,4) and c['pe'] in (1,2):selected.append(r)
        elif c.get('product_profile')=='pipelined' and c['lanes']==2 and c['pe']==1:selected.append(r)
    if len(selected)!=5:raise ValueError('expected the passing baseline plus four qualified registered Montgomery points')
    if any(r['workload']!=selected[0]['workload'] or r['max_abs_error']!=0 or not reusable(r,Path(r['evidence_root']),r) for r in selected):
        raise ValueError('frontier requires identical exact workloads and intact qualification evidence')
    return sorted(selected,key=lambda r:(r['configuration']['product_profile']!='pipelined',r['configuration']['lanes'],r['configuration']['pe'])),sources


def table_rows(state,rows,target):
    result=[]
    for r in rows:
        name=r['name'];e=state['routed'].get(name,{});c=r['configuration'];m=e.get('metrics',{})
        result.append(dict(name=name,workload=r['workload_name'],profile=c['product_profile'],lanes=c['lanes'],pe=c['pe'],
            family=c['product_profile'],recipe=e.get('target',{}).get('implementation_directive',''),
            mapped_passed=state['mapped'].get(name,{}).get('passed',False),routed_passed=e.get('passed',False),
            feasible=name in state['feasible'],pareto=name in state['frontiers']['full-ternary'],
            error_bound=r['max_abs_error'],latency_cycles=r['latency_cycles'],initiation_interval_cycles=r['initiation_interval_cycles'],
            **m,**device.performance(r,target)))
    return result


def save(out,state,rows,target):
    points=table_rows(state,rows,target)
    state['frontiers']['full-ternary']=nondominated([p for p in points if p['feasible']])
    points=table_rows(state,rows,target)
    write_json(out/'results.json',state)
    fields=['name','workload','profile','lanes','pe','recipe','mapped_passed','routed_passed','feasible','pareto',
            *device.RESOURCES,'setup_slack_ns','hold_slack_ns','pulse_slack_ns','error_bound','latency_cycles',
            'initiation_interval_cycles','modeled_products_per_second']
    with (out/'points.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(points)
    lines=['# Routed 250 MHz polynomial multiplication frontier','',
        'Exact N=512 full32 × ternary negacyclic products modulo 2^32. '
        'Registered on-chip harness v2; total resources include source/sink logic.','',
        f"Status: {state['status']}. Feasible: {len(state['feasible'])}; nondominated: {len(state['frontiers']['full-ternary'])}. "
        f"New mapped attempts: {state['new_mapped']}; new routed attempts: {state['new_routed']}. "
        'The previously qualified baseline is imported and not charged as a new evaluation.','',
        '| Profile | Lanes | PEs | LUTs | FFs | DSPs | BRAM36 | Interval | Products/s* | Setup ns | Hold ns | Feasible | Pareto |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |']
    for p in points:
        def value(k):return f"{p[k]:g}" if k in p else '—'
        lines.append(f"| {p['profile']} | {p['lanes']} | {p['pe']} | {value('lut')} | {value('ff')} | {value('dsp')} | {value('bram36')} | {p['initiation_interval_cycles']} | {p['modeled_products_per_second']:.1f} | {value('setup_slack_ns')} | {value('hold_slack_ns')} | {p['feasible']} | {p['pareto']} |")
    lines+=['','*Products/s are modeled from the qualified kernel interval at 250 MHz and the fixed bandwidth assumption; '
        'harness stimulus is not a throughput measurement. Rates shown for timing-failing/pending designs are not achieved results.','',
        'Pareto objectives minimize error, LUT/FF/DSP/BRAM36/URAM use and latency, and maximize modeled throughput. '
        'Only fully routed timing-feasible points with verified clock routes enter the frontier. '
        'Rings in the plot indicate this complete frontier; a projection need not form a two-dimensional frontier.','',
        '[CSV](points.csv) · [Evidence and attempt history](results.json)','',
        '![Routed timing-qualified resource/throughput tradeoffs](frontier.svg)','']
    (out/'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,action='append',required=True)
    p.add_argument('--seed-campaign',type=Path,default=ROOT/'build/timing-closure-512-onchip')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--target',type=Path,default=ROOT/'studies/u280-kernel-harness.json')
    p.add_argument('--max-repairs',type=int,default=2)
    p.add_argument('--timeout',type=int,default=3600)
    p.add_argument('--vivado',type=Path,default=Path('/home/opt/xilinx/Vivado/2023.2/bin/vivado'))
    args=p.parse_args(argv)
    if args.max_repairs not in range(3) or args.timeout<=0:raise ValueError('invalid repair budget or timeout')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    with (out/'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        target=device.load_target(args.target)
        if target['clock_mhz']!=250 or target.get('implementation_context')!=timing_harness.CONTEXT or target['implementation_directive']!='Default':
            raise ValueError('expected unchanged default 250 MHz on-chip harness context')
        rows,sources=rows_for_frontier(args.campaign);byname={r['name']:r for r in rows}
        seed_path=args.seed_campaign.resolve()/'results.json';seed=json.loads(seed_path.read_text())
        if seed.get('status')!='complete' or not seed.get('winner'):raise ValueError('seed must be a completed timing-qualified closure run')
        original=seed['winner']['row'];base=byname[original['name']]
        if any(original[k]!=base[k] for k in ('rtl_sha256','configuration','workload','latency_cycles','initiation_interval_cycles')):
            raise ValueError('seed workload, timing or RTL differs')
        tool=backend.tool_identity(args.vivado,out)
        code=[Path(__file__),ROOT/'scripts/find_timing_met.py',ROOT/'scripts/device_polynomial_study.py',
              ROOT/'architecture_search/device.py',ROOT/'architecture_search/device_evaluate.py',ROOT/'architecture_search/timing_harness.py',
              ROOT/'architecture_search/model.py',ROOT/'scripts/polynomial_study.py']
        manifest=dict(schema='routed-frontier-v1',target=target,tool=tool,sources=sources,seed_sha256=file_hash(seed_path),
            plan=dict(candidates=5,new_mapped_budget=4,new_routed_budget=4+args.max_repairs),error_limit=0,
            code={str(f.relative_to(ROOT)):file_hash(f) for f in code})
        mf=out/'manifest.json'
        if mf.exists() and json.loads(mf.read_text())!=manifest:raise ValueError('frontier manifest differs; use a new output directory')
        prior=json.loads((out/'results.json').read_text()) if (out/'results.json').exists() else {}
        prior_history={h['evidence']:h for h in prior.get('history',[])}
        prior_elapsed=max((h['elapsed_seconds'] for h in prior.get('history',[])),default=0)
        if prior.get('active'):prior_elapsed+=max(0,time.time()-prior['active']['started_at'])
        write_json(mf,manifest)
        state=dict(schema='routed-frontier-results-v1',status='running',policy='frontier-extension',seed=0,
            mapped={},routed={},route_attempts={},clock_checks={},feasible=[],frontiers={'full-ternary':[]},history=[],
            new_mapped=0,new_routed=0,active=None)
        started=time.monotonic()

        def check_evidence(row,e,stage):
            if e.get('stage')!=stage or e.get('tool')!=tool or not same_context(e.get('target',{}),target) or e.get('rtl_sha256')!=row['rtl_sha256'] or evidence_integrity(e)!='verified':
                raise ValueError('changed implementation evidence for '+row['name'])

        def qualify(row,e):
            if not device.feasible(row,e,e['target'],0):return False
            folder=Path(e['checkpoint']).parent
            counts=endpoint_counts((folder/'timing.rpt').read_text())
            if counts is None or any(counts.values()):return False
            clock_folder=out/'clock-checks'/(row['name']+'-'+e['target']['implementation_directive'])
            ok=verify_clock(e['checkpoint'],args.vivado,clock_folder)
            if ok:state['clock_checks'][row['name']]=str(clock_folder/'evidence.json')
            return ok

        def record(row,e,ef,imported=False):
            stage=e['stage'];check_evidence(row,e,stage);name=row['name']
            if stage=='mapped':state['mapped'][name]=e
            else:
                state['route_attempts'].setdefault(name,{})[e['target']['implementation_directive']]=str(ef)
                state['routed'][name]=e
                if qualify(row,e) and name not in state['feasible']:state['feasible'].append(name)
            if not imported:state['new_'+stage]+=1
            state['active']=None
            state['history'].append(dict(name=name,stage=stage,phase='imported' if imported else 'extension',
                evidence=str(ef),passed=e['passed'],evaluation_count=state['new_mapped']+state['new_routed'],
                elapsed_seconds=prior_history.get(str(ef),{}).get('elapsed_seconds',prior_elapsed+time.monotonic()-started),best_feasible_rates={'full-ternary':max(
                    (device.performance(byname[n],target)['modeled_products_per_second'] for n in state['feasible']),default=None)}))
            save(out,state,rows,target)

        def measure(row,stage,recipe='Default',previous=None):
            folder=out/row['name']/(stage+'-'+recipe);ef=folder/'evidence.json';t={**target,'implementation_directive':recipe}
            if ef.exists():
                e=json.loads(ef.read_text());check_evidence(row,e,stage)
                if e['target']!=t:raise ValueError('cached implementation recipe differs')
            else:
                if (folder/'run.tcl').exists():
                    needle=str(folder/'run.tcl').encode()
                    for proc in Path('/proc').glob('[0-9]*/cmdline'):
                        try:live=needle in proc.read_bytes().split(b'\0')
                        except OSError:continue
                        if live:raise ValueError('interrupted Vivado trial is still running')
                    log=folder/'interrupted.log';log.write_text('Unsealed interrupted evaluation; charged as failed.\n')
                    e=dict(stage=stage,target=t,tool=tool,rtl_sha256=row['rtl_sha256'],passed=False,metrics={},checkpoint=str(folder/'design.dcp'),reason='interrupted')
                    e['integrity']=dict(version=1,inputs_unchanged=True,inputs=artifact_manifest([row['rtl_path']]),outputs=artifact_manifest([log]),measurement={k:e[k] for k in ('stage','target','tool','rtl_sha256','passed','metrics','checkpoint')})
                    write_json(ef,e)
                else:
                    state['active']=dict(name=row['name'],stage=stage,recipe=recipe,started_at=time.time());save(out,state,rows,target)
                    print(stage,row['name'],recipe,flush=True)
                    e=backend.evaluate(row,row['rtl_path'],t,tool,args.vivado,folder,stage,previous,args.timeout,4)
            record(row,e,ef);return e

        for a in seed['attempts']:
            ef=Path(a['evidence']);e=json.loads(ef.read_text())
            if e['rtl_sha256']==base['rtl_sha256']:record(base,e,ef,True)
        if base['name'] not in state['feasible']:raise ValueError('imported baseline is no longer timing-qualified')
        new=[r for r in rows if r['name']!=base['name']]
        for row in new:
            mapped=measure(row,'mapped')
            if mapped['passed'] and device.resources_fit(mapped['metrics'],target):measure(row,'routed',previous=mapped)
        failed=[r for r in new if r['name'] not in state['feasible'] and state['routed'].get(r['name'],{}).get('passed')]
        failed.sort(key=lambda r:(-state['routed'][r['name']]['metrics']['setup_slack_ns'],r['name']))
        for row in failed[:args.max_repairs]:
            previous=state['routed'][row['name']];m=previous['metrics']
            hold_only=m['setup_slack_ns']>=0 and m['hold_slack_ns']<0
            measure(row,'routed','HoldFix' if hold_only else 'ExploreHoldFix',previous if hold_only else state['mapped'][row['name']])
        for name in state['feasible']:
            row=byname[name];e=state['routed'][name];source=Path(e['checkpoint']).parent;dest=out/'exports'/name;dest.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(row['rtl_path'],dest/'SearchTop.sv')
            for filename in ('TimingHarness.sv','constraints.xdc','design.dcp','timing.rpt','utilization.rpt','hierarchical-utilization.rpt','clock-utilization.rpt','drc.rpt'):
                shutil.copyfile(source/filename,dest/filename)
            write_json(dest/'manifest.json',dict(configuration=row['configuration'],workload=row['workload'],target=e['target'],tool=tool,
                metrics=e['metrics'],rtl_sha256=row['rtl_sha256'],clock_evidence=state['clock_checks'][name],
                files=artifact_manifest([f for f in dest.iterdir() if f.name!='manifest.json'])))
        state['status']='complete';save(out,state,rows,target)
        print(f"Complete: {len(state['feasible'])} timing-qualified points; {len(state['frontiers']['full-ternary'])} Pareto points.",flush=True)
        return 0


if __name__=='__main__':raise SystemExit(main())
