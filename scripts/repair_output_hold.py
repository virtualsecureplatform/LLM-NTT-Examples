#!/usr/bin/env python3
"""Repair output hold paths in a verified routed checkpoint without changing RTL."""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from architecture_search.model import artifact_manifest,evidence_integrity,file_hash,metric_number,run,write_json


def parse_reports(directory):
    metrics={}
    aliases={'CLB LUTs':'lut','Slice LUTs':'lut','CLB Registers':'ff','Slice Registers':'ff',
             'DSPs':'dsp','DSP':'dsp','Block RAM Tile':'bram','URAM':'uram'}
    utilization=directory/'utilization_route.rpt'
    if utilization.exists():
        for line in utilization.read_text().splitlines():
            cells=[c.strip() for c in line.split('|')[1:-1]]
            if len(cells)<2 or cells[0] not in aliases:continue
            try:value=float(cells[1].replace(',',''))
            except ValueError:continue
            if metric_number(value):metrics.setdefault(aliases[cells[0]],value)
    props=directory/'timing.properties'
    if props.exists():
        for line in props.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and key in ('wns_ns','hold_slack_ns','added_output_luts'):
                try:number=float(value)
                except ValueError:continue
                if metric_number(number):metrics[key]=number
    route=directory/'route_status.rpt'
    text=route.read_text() if route.exists() else ''
    counts=[]
    for label in ('routable nets','fully routed nets','nets with routing errors'):
        match=re.search(r'# of '+label+r'\.+\s*:\s*([0-9,]+)',text)
        counts.append(int(match.group(1).replace(',','')) if match else None)
    complete=counts[0] is not None and counts[0]>0 and counts[1]==counts[0] and counts[2]==0
    return metrics,complete


def validate_source(report):
    if len(report.get('candidates',[]))!=1:raise ValueError('Expected exactly one candidate')
    record=report['candidates'][0];evidence=record.get('evidence',{}).get('route',{})
    if record.get('correct') is not True or evidence.get('implementation_passed') is not True:
        raise ValueError('Requires correct RTL and completed routing')
    if evidence_integrity(evidence)!='verified':raise ValueError('Source route integrity is not verified')
    if not metric_number(evidence.get('metrics',{}).get('wns_ns')) or evidence['metrics']['wns_ns']<0:
        raise ValueError('Output hold repair requires nonnegative source setup slack')
    rtl=Path(record['rtl_path'])
    if not rtl.is_absolute():rtl=ROOT/rtl
    if file_hash(rtl)!=record.get('rtl_hash'):raise ValueError('Source RTL changed')
    checkpoint=Path(evidence['reports']['checkpoint'])
    if not checkpoint.is_absolute():checkpoint=ROOT/checkpoint
    if not checkpoint.is_file():raise ValueError('Source checkpoint missing')
    return record,evidence,rtl,checkpoint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--max-passes',type=int,choices=range(1,5),default=2)
    parser.add_argument('--timeout',type=float,default=7200)
    a=parser.parse_args()
    if not metric_number(a.timeout) or a.timeout<=0:parser.error('timeout must be positive and finite')
    source=a.report.resolve();report=json.loads(source.read_text())
    record,old,rtl,checkpoint=validate_source(report)
    out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):parser.error('Use a fresh output directory')
    out.mkdir(parents=True,exist_ok=True)
    script=out/'repair.tcl';shutil.copyfile(ROOT/'scripts/repair_output_hold.tcl',script)
    target={**old['target'],'output_hold_eco':{'max_passes':a.max_passes,'fixed_existing_placement':True}}
    write_json(out/'manifest.json',{'campaign':{'workload':report['workload'],'target':target,'stages':['simulation','route']},
        'source_report':str(source),'source_report_sha256':file_hash(source),'source_checkpoint_sha256':file_hash(checkpoint),
        'scope':'Same RTL and original timing constraints; add identity LUTs only to negative output hold paths. Existing placement fixed; added resources measured.'})
    inputs=artifact_manifest([source,rtl,checkpoint,script,Path(__file__),out/'manifest.json'])
    start=time.monotonic();process={'returncode':1,'error':'Vivado queue timeout'};queued=0
    with Path(tempfile.gettempdir(),f'ntt-search-vivado-{os.getuid()}.lock').open('a') as lock:
        while time.monotonic()-start<a.timeout:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:time.sleep(min(.2,max(0,a.timeout-(time.monotonic()-start))))
        else:lock=None
        queued=time.monotonic()-start
        if lock is not None:
            vivado=target.get('vivado',f"/home/opt/xilinx/Vivado/{target.get('tool_version','2023.2')}/bin/vivado")
            process=run([vivado,'-mode','batch','-nojournal','-nolog','-source',str(script),'-tclargs',str(checkpoint),str(out),str(a.max_passes)],
                        ROOT,out/'repair.log',max(0,a.timeout-queued))
    metrics,complete=parse_reports(out)
    for name in ('transaction_ns','latency_ns','transforms_per_second'):
        if name in old.get('metrics',{}):metrics[name]=old['metrics'][name]
    clean=all(metric_number(metrics.get(k)) and metrics[k]>=0 for k in ('wns_ns','hold_slack_ns'))
    artifacts={'checkpoint':'repaired_route.dcp','route_status':'route_status.rpt','timing':'timing_summary_route.rpt',
               'timing_properties':'timing.properties','utilization':'utilization_route.rpt','repair_map':'output_hold_repairs.txt','repair_tcl':'repair.tcl'}
    reports={k:str(out/name) for k,name in artifacts.items() if (out/name).exists()}
    implemented=process['returncode']==0 and complete and 'checkpoint' in reports
    unchanged=inputs==artifact_manifest(inputs['files'],inputs['directories']) and evidence_integrity(old)=='verified'
    evidence={'passed':implemented and clean and unchanged,'implementation_passed':implemented,'timing_clean':clean,
              'target':target,'metrics':metrics,'process':process,'reports':reports,'queue_seconds':queued}
    if not unchanged:evidence['error']='Source evidence changed during repair'
    outputs=artifact_manifest([*map(Path,reports.values()),out/'repair.log'])
    evidence['integrity']={'version':1,'inputs_unchanged':unchanged,'inputs':inputs,'outputs':outputs,
        'measurement':copy.deepcopy({k:evidence[k] for k in ('passed','implementation_passed','timing_clean','target','metrics')})}
    updated=copy.deepcopy(record);updated['evidence']['route']=evidence
    updated['status']='complete' if evidence['passed'] else 'hardware_failed'
    updated['route_repair_source']={'report':str(source),'sha256':file_hash(source)}
    write_json(out/'record.json',updated)
    write_json(out/'report.json',{**report,'candidates':[updated],'frontiers':{}})
    print(json.dumps({'passed':evidence['passed'],'metrics':metrics,'queue_seconds':queued}),flush=True)
    return 0 if evidence['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
