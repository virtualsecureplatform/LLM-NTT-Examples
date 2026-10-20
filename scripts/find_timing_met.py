#!/usr/bin/env python3
"""Bounded timing closure of one N512 Montgomery product in an on-chip harness."""
import argparse
import csv
import fcntl
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from architecture_search import device,device_evaluate as backend,timing_harness
from architecture_search.model import artifact_manifest,evidence_integrity,file_hash,write_json,run
from scripts.device_polynomial_study import inventory
from scripts.polynomial_study import reusable


def candidate(campaign,profile):
    rows,_=inventory([campaign])
    options=[r for r in rows if r['workload_name']=='full-ternary' and r['workload']['n']==512
             and all(r['configuration'].get(k)==v for k,v in dict(generator='ngen',backend='streamed',
                 reduction='montgomery',lanes=2,pe=1,radix=2,product_profile=profile).items())]
    if len(options)!=1:raise ValueError('need one qualified '+profile+' Montgomery candidate')
    r=options[0]
    if not reusable(r,Path(r['evidence_root']),r):raise ValueError('changed qualification evidence')
    return r


def write_report(out,attempts,winner):
    fields=['profile','recipe','stage','passed','feasible','setup_slack_ns','hold_slack_ns','pulse_slack_ns',*device.RESOURCES,'evidence']
    with (out/'attempts.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fields,extrasaction='ignore');writer.writeheader();writer.writerows(attempts)
    lines=['# N512 timing closure at 250 MHz','',
           'Registered on-chip source/sink harness with a routed BUFG clock. Resources include the harness. '
           'This is kernel-harness qualification, not a board measurement.','',
           '| Profile | Recipe | Stage | Setup (ns) | Hold (ns) | Feasible |',
           '| --- | --- | --- | ---: | ---: | --- |']
    for a in attempts:lines.append(f"| {a['profile']} | {a['recipe']} | {a['stage']} | {a.get('setup_slack_ns','—')} | {a.get('hold_slack_ns','—')} | {a['feasible']} |")
    lines+=['',('Qualified: '+winner['name'] if winner else 'No fully qualified timing-met option yet.'),
            '', 'See attempts.csv, results.json, and the per-attempt sealed implementation evidence.']
    (out/'summary.md').write_text('\n'.join(lines)+'\n')


def verify_clock(checkpoint,vivado,directory):
    """Read-only signoff probe: verify the actual BUFG output net is routed."""
    directory.mkdir(parents=True,exist_ok=True);cp=Path(checkpoint).resolve()
    ef=directory/'evidence.json'
    if ef.exists():
        e=json.loads(ef.read_text())
        if e.get('checkpoint_sha256')!=file_hash(cp) or evidence_integrity(e)!='verified':raise ValueError('changed clock probe evidence')
        return e['passed']
    q=backend.tcl_word;tcl=directory/'inspect.tcl';report=directory/'clock-routing.rpt'
    tcl.write_text(f'''set_param general.maxThreads 4
open_checkpoint {q(cp)}
set buffers [get_cells -hier -filter {{REF_NAME =~ BUFG*}}]
if {{[llength $buffers]<1 || [llength [get_clocks]]!=1}} {{error "expected one buffered global clock"}}
set clock_nets [get_nets -of_objects [get_pins -of_objects $buffers -filter {{REF_PIN_NAME == O}}]]
if {{[llength $clock_nets]!=[llength $buffers]}} {{error "missing buffered clock net"}}
set stream [open {q(report)} w]
foreach net $clock_nets {{
set status [get_property ROUTE_STATUS $net]
puts $stream "clock_net $net route_status $status"
if {{$status ne "ROUTED"}} {{error "global clock net is not routed"}}
}}
close $stream
report_route_status -file {q(directory/'route-status.rpt')}
exit
''')
    inputs=artifact_manifest([cp,tcl])
    process=run([str(vivado),'-mode','batch','-nojournal','-log',str(directory/'vivado.log'),'-source',str(tcl)],ROOT,directory/'process.log',180)
    e=dict(passed=process['returncode']==0,checkpoint_sha256=file_hash(cp),process=process)
    e['integrity']=dict(version=1,inputs_unchanged=inputs==artifact_manifest(inputs['files']),inputs=inputs,
        outputs=artifact_manifest([f for f in directory.iterdir() if f.suffix in ('.log','.rpt')]),
        measurement={k:e[k] for k in ('passed','checkpoint_sha256')})
    write_json(ef,e);return e['passed']


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,default=ROOT/'build/polynomial-study-512-pipelined-reductions')
    p.add_argument('--registered-campaign',type=Path,default=ROOT/'build/polynomial-study-512-registered')
    p.add_argument('--initial-campaign',type=Path,help='Adopt a completed, sealed default-harness attempt')
    p.add_argument('--registered-mapping',type=Path,help='Reuse an intact registered-profile mapped evidence file')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--target',type=Path,default=ROOT/'studies/u280-kernel-harness.json')
    p.add_argument('--vivado',type=Path,default=Path('/home/opt/xilinx/Vivado/2023.2/bin/vivado'))
    p.add_argument('--timeout',type=int,default=3600)
    args=p.parse_args(argv)
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    with (out/'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        target=device.load_target(args.target)
        if target.get('implementation_context')!=timing_harness.CONTEXT or target['clock_mhz']!=250 or target['implementation_directive']!='Default':
            raise ValueError('expected the default 250 MHz registered-harness target')
        current=candidate(args.campaign,'pipelined')
        # Fallback qualification may still be running; it is only needed after the first candidate fails.
        tool=backend.tool_identity(args.vivado,out)
        paths=[Path(__file__),ROOT/'architecture_search/device.py',ROOT/'architecture_search/device_evaluate.py',ROOT/'architecture_search/timing_harness.py']
        manifest=dict(target=target,tool=tool,kernel=current['rtl_sha256'],
            registered_campaign=str(args.registered_campaign.resolve()),initial_campaign=str(args.initial_campaign.resolve()) if args.initial_campaign else None,
            registered_mapping=str(args.registered_mapping.resolve()) if args.registered_mapping else None,
            sources={str(f.relative_to(ROOT)):file_hash(f) for f in paths},max_design_mappings=2,max_routed_attempts=4)
        mf=out/'manifest.json'
        if mf.exists() and json.loads(mf.read_text())!=manifest:raise ValueError('closure manifest differs; use a new output directory')
        write_json(mf,manifest);attempts=[];winner=None

        def record(row,e,evidence):
            ok=device.feasible(row,e,e['target'],0)
            if ok:ok=verify_clock(e['checkpoint'],args.vivado,out/'clock-checks'/(row['name']+'-'+e['target']['implementation_directive']))
            attempts.append(dict(profile=row['configuration']['product_profile'],recipe=e['target']['implementation_directive'],
                stage=e['stage'],passed=e['passed'],feasible=ok,**e['metrics'],evidence=str(evidence)))
            write_json(out/'results.json',dict(status='running',attempts=attempts,winner=None))
            write_report(out,attempts,None)
            return ok

        def measure(row,stage,recipe='Default',previous=None):
            t={**target,'implementation_directive':recipe}
            directory=out/row['configuration']['product_profile']/(stage+'-'+recipe)
            ef=directory/'evidence.json'
            if ef.exists():
                e=json.loads(ef.read_text())
                if e.get('target')!=t or e.get('tool')!=tool or e.get('rtl_sha256')!=row['rtl_sha256'] or evidence_integrity(e)!='verified':
                    raise ValueError('cached closure evidence differs')
            else:
                if (directory/'run.tcl').exists():raise ValueError('unsealed interrupted attempt; inspect before retrying')
                print(row['configuration']['product_profile'],stage,recipe,flush=True)
                e=backend.evaluate(row,row['rtl_path'],t,tool,args.vivado,directory,stage,previous,args.timeout,4)
            return e,ef

        for profile in ('pipelined','registered'):
            row=current if profile=='pipelined' else candidate(args.registered_campaign,'registered')
            if profile=='pipelined' and args.initial_campaign:
                old=json.loads((args.initial_campaign/'results.json').read_text())
                if old.get('status')!='complete' or old.get('active'):raise ValueError('initial campaign is not complete')
                mapped=old['mapped'][row['name']];routed=old['routed'].get(row['name'])
                for e in (mapped,*([routed] if routed else [])):
                    if e['target']!=target or e['tool']!=tool or e['rtl_sha256']!=row['rtl_sha256'] or evidence_integrity(e)!='verified':
                        raise ValueError('invalid adopted evidence')
                mapfile=args.initial_campaign/row['name']/'mapped/evidence.json'
                routefile=args.initial_campaign/row['name']/'routed/evidence.json'
            elif profile=='registered' and args.registered_mapping:
                mapfile=args.registered_mapping.resolve();mapped=json.loads(mapfile.read_text());routed=None
                if mapped.get('stage')!='mapped' or mapped.get('target')!=target or mapped.get('tool')!=tool or mapped.get('rtl_sha256')!=row['rtl_sha256'] or evidence_integrity(mapped)!='verified':
                    raise ValueError('invalid adopted registered mapping')
            else:
                mapped,mapfile=measure(row,'mapped');routed=None
            record(row,mapped,mapfile)
            if not mapped['passed'] or not device.resources_fit(mapped['metrics'],target):continue
            if routed is None:routed,routefile=measure(row,'routed',previous=mapped)
            if record(row,routed,routefile):winner=dict(name=row['name'],row=row,evidence=str(routefile));break
            if not routed['passed']:continue
            m=routed['metrics'];hold_only=m['setup_slack_ns']>=0 and m['hold_slack_ns']<0
            if profile=='pipelined' and not hold_only:continue
            recipe='HoldFix' if hold_only else 'ExploreHoldFix'
            repaired,repairfile=measure(row,'routed',recipe,routed if hold_only else mapped)
            if record(row,repaired,repairfile):winner=dict(name=row['name'],row=row,evidence=str(repairfile));break

        if winner:
            e=json.loads(Path(winner['evidence']).read_text());route=Path(winner['evidence']).parent
            dest=out/'exports'/winner['name'];dest.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(winner['row']['rtl_path'],dest/'SearchTop.sv')
            for name in ('TimingHarness.sv','constraints.xdc','design.dcp','timing.rpt','utilization.rpt','hierarchical-utilization.rpt','clock-utilization.rpt','harness-checks.rpt','drc.rpt'):
                shutil.copyfile(route/name,dest/name)
            clock_check=out/'clock-checks'/(winner['name']+'-'+e['target']['implementation_directive'])
            for name in ('clock-routing.rpt','route-status.rpt','evidence.json'):
                shutil.copyfile(clock_check/name,dest/('clock-'+name))
            write_json(dest/'manifest.json',dict(scope=e['scope'],target=e['target'],tool=tool,workload=winner['row']['workload'],
                configuration=winner['row']['configuration'],latency_cycles=winner['row']['latency_cycles'],
                initiation_interval_cycles=winner['row']['initiation_interval_cycles'],metrics=e['metrics'],
                original_evidence=winner['evidence'],original_evidence_sha256=file_hash(Path(winner['evidence'])),
                harness_validation=e['harness_validation'],files=artifact_manifest([f for f in dest.iterdir() if f.name!='manifest.json'])))
        write_json(out/'results.json',dict(status='complete' if winner else 'budget-exhausted',attempts=attempts,winner=winner))
        write_report(out,attempts,winner)
        print('Timing qualified: '+winner['name'] if winner else 'No timing-qualified option within budget.',flush=True)
        return 0 if winner else 1


if __name__=='__main__':raise SystemExit(main())
