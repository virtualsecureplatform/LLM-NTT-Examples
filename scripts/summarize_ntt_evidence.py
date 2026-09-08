#!/usr/bin/env python3
"""Consolidate measured comparisons without mixing workloads or evidence stages."""
import argparse
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import evidence_integrity,file_hash,frontier,write_json

ROOT=Path(__file__).resolve().parents[1]


def summarize(report,campaign,stage):
    if report['workload']!=campaign['workload']:raise ValueError('comparison workload mismatch')
    objectives={'lut':'min','ff':'min','dsp':'min','bram':'min','uram':'min'}
    if campaign['workload']['kind']=='preset':objectives['transaction_ns']='min'
    else:objectives.update(latency_ns='min',transforms_per_second='max')
    records=copy.deepcopy(report['candidates']);rows=[]
    for r in records:
        e=r.get('evidence',{}).get(stage,{})
        integrity=evidence_integrity(e)
        path=r.get('rtl_path') or r.get('provenance',{}).get('stream',{}).get('rtl')
        rtl_state='unavailable'
        if path:
            rtl_state='verified' if Path(path).is_file() and file_hash(Path(path))==r.get('rtl_hash') else 'invalid'
        if rtl_state!='verified' or integrity=='invalid' or r.get('status') not in ('complete','hardware_failed'):
            e['passed']=False
        eligible=bool(frontier([r],objectives,stage,campaign['target'],campaign.get('resource_limits',{})))
        rows.append({'id':r['id'],'configuration':r['configuration'],'status':r.get('status'),
                     'correct':r.get('correct') is True,'stage':stage,'qualified':eligible,
                     'artifact_integrity':integrity,'rtl_integrity':rtl_state,
                     'metrics':e.get('metrics',{}),'cycle_metrics':r.get('evidence',{}).get('simulation',{}).get('metrics',{})})
    return {'workload':campaign['workload'],'target':campaign['target'],'stage':stage,'rows':rows,
            'frontier':frontier(records,objectives,stage,campaign['target'],campaign.get('resource_limits',{}))}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();index=json.loads(a.index.read_text());out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('use a fresh output directory')
    inputs={str(a.index.resolve()):file_hash(a.index)};sections=[];missing=[]
    for item in index['comparisons']:
        directory=ROOT/item['directory'];paths=[directory/'manifest.json',directory/'report.json']
        if not all(path.exists() for path in paths):
            missing.append(item);continue
        manifest,report=[json.loads(path.read_text()) for path in paths]
        for name,expected in manifest.get('artifact_hashes_at_import',{}).items():
            if not Path(name).is_file() or file_hash(Path(name))!=expected:raise ValueError('imported artifact changed: '+name)
        inputs.update({str(path.resolve()):file_hash(path) for path in paths})
        if manifest['campaign'].get('bandwidth') or manifest['campaign'].get('requirements'):
            p.error('bandwidth-constrained comparison requires its dedicated policy report')
        sections.append({'name':item['name'],'source':str(directory),'notes':item.get('notes',''),
                         **summarize(report,manifest['campaign'],item['stage'])})
    result={'schema':'ntt-evidence-snapshot-v1','sections':sections,'missing_comparisons':missing,'inputs':inputs,
            'qualification':'Synthesis qualification requires completed implementation and nonnegative setup slack; it does not establish routed timing closure. Route qualification additionally requires nonnegative hold slack and completed routing. Rates at synthesis are estimates under the stated target clock.',
            'scope':'Snapshot of named comparisons, not certification that the full project plan is complete. Legacy hardware evidence remains explicitly unverified by newer manifests.'}
    write_json(out/'report.json',result)
    lines=['# NTT generator evidence snapshot','',result['scope'],'',result['qualification'],'']
    for section in sections:
        lines += ['## '+section['name'],'',section['notes'],'',
                  'Workload: `'+json.dumps(section['workload'],sort_keys=True)+'`','',
                  'Target: `'+json.dumps(section['target'],sort_keys=True)+'`','',
                  'Stage: **'+section['stage']+'**. Source: `'+section['source']+'`.','',
                  '| Candidate | Configuration | Correct | Qualified | LUT | FF | DSP | BRAM | WNS ns | Hold ns | Integrity |',
                  '| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
        for row in section['rows']:
            m=row['metrics'];values=[row['id'][:12],json.dumps(row['configuration'],sort_keys=True),str(row['correct']),str(row['qualified']),
                                    *[str(m.get(k,'unmeasured')) for k in ('lut','ff','dsp','bram','wns_ns','hold_slack_ns')],row['artifact_integrity']]
            lines.append('| '+' | '.join(values)+' |')
        lines+=['','| Candidate | Latency/transaction cycles | Frame interval cycles | Qualified latency/transaction ns | Qualified transforms/s |',
                '| --- | ---: | ---: | ---: | ---: |']
        for row in section['rows']:
            m=row['metrics'];cycles=row['cycle_metrics'];preset=section['workload']['kind']=='preset'
            latency=cycles.get('transaction_cycles' if preset else 'latency_cycles','unmeasured')
            interval=cycles.get('initiation_interval_cycles','not measured')
            ns=m.get('transaction_ns' if preset else 'latency_ns','unmeasured') if row['qualified'] else 'unqualified'
            rate='not measured' if preset else m.get('transforms_per_second','unmeasured') if row['qualified'] else 'unqualified'
            lines.append(f"| {row['id'][:12]} | {latency} | {interval} | {ns} | {rate} |")
        lines+=['','Qualified frontier: '+(', '.join(key[:12] for key in section['frontier']) or 'none')+'.','']
    if missing:
        lines+=['## Pending comparisons','']+[f"- {item['name']}: `{item['directory']}`" for item in missing]+['']
    (out/'report.md').write_text('\n'.join(lines))
    print(out/'report.md')

if __name__=='__main__':main()
