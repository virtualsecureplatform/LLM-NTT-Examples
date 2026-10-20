#!/usr/bin/env python3
"""Publish compact verified snapshots of a completed 250 MHz frontier extension."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from architecture_search import device
from architecture_search.model import evidence_integrity,file_hash,write_json
from scripts.device_polynomial_study import inventory
from scripts.extend_timing_frontier import same_context,endpoint_counts,nondominated,table_rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,default=ROOT/'docs/results');p.add_argument('--prefix',default='pareto250-512')
    args=p.parse_args();root=args.campaign.resolve();out=args.output_dir;prefix=args.prefix
    if Path(prefix).name!=prefix or not prefix:raise ValueError('prefix must be a filename component')
    manifest=json.loads((root/'manifest.json').read_text());state=json.loads((root/'results.json').read_text())
    if state['status']!='complete' or state['active']:raise ValueError('frontier campaign is not complete')
    for source in manifest['sources']:
        path=Path(source['results'])
        if file_hash(path)!=source['results_sha256'] or file_hash(path.parent/'manifest.json')!=source['manifest_sha256']:
            raise ValueError('qualification source changed')
    rows,_=inventory([Path(s['results']).parent for s in manifest['sources']]);byname={r['name']:r for r in rows}
    selected=[byname[n] for n in state['mapped']];valid=[];snapshots=[];harness_hashes=set()
    for row in selected:
        name=row['name'];e=state['routed'].get(name);good=False
        if e:
            if not same_context(e['target'],manifest['target']) or evidence_integrity(e)!='verified':raise ValueError('invalid routed measurement')
            harness_hashes.add(e.get('harness_sha256'))
            if device.feasible(row,e,e['target'],0):
                counts=endpoint_counts((Path(e['checkpoint']).parent/'timing.rpt').read_text())
                proof_path=Path(state['clock_checks'].get(name,root/'clock-checks'/(name+'-'+e['target']['implementation_directive'])/'evidence.json'))
                if counts and not any(counts.values()) and proof_path.exists():
                    proof=json.loads(proof_path.read_text())
                    good=bool(proof['passed'] and evidence_integrity(proof)=='verified'
                              and proof['checkpoint_sha256']==file_hash(Path(e['checkpoint'])))
        if good:valid.append(name)
        snapshots.append(dict(name=name,configuration=row['configuration'],workload=row['workload'],
            latency_cycles=row['latency_cycles'],initiation_interval_cycles=row['initiation_interval_cycles'],
            rtl_sha256=row['rtl_sha256'],qualification_corpus_sha256=row['corpus_sha256'],
            harness_sha256=e.get('harness_sha256') if e else None,
            feasible=good,pareto=name in state['frontiers']['full-ternary'],
            mapped_metrics=state['mapped'][name].get('metrics'),routed_metrics=e.get('metrics') if e else None,
            recipe=e['target']['implementation_directive'] if e else None,
            routed_evidence_sha256=file_hash(Path(e['checkpoint']).parent/'evidence.json') if e else None,
            clock_evidence=state['clock_checks'].get(name),
            clock_evidence_sha256=file_hash(Path(state['clock_checks'][name])) if name in state['clock_checks'] else None))
    if len(harness_hashes)!=1 or None in harness_hashes:raise ValueError('comparison requires identical generated harness RTL')
    if set(valid)!=set(state['feasible']):raise ValueError('published feasibility disagrees with verified measurements')
    points=table_rows(state,selected,manifest['target'])
    if set(nondominated([r for r in points if r['feasible']]))!=set(state['frontiers']['full-ternary']):raise ValueError('Pareto membership differs')
    out.mkdir(parents=True,exist_ok=True)
    for ext in ('csv','svg','png'):
        source=root/('points.csv' if ext=='csv' else 'frontier.'+ext)
        shutil.copyfile(source,out/(prefix+'.'+ext))
    snapshot=dict(schema='routed-frontier-snapshot-v1',manifest=manifest,campaign=str(root),
        results_sha256=file_hash(root/'results.json'),new_mapped=state['new_mapped'],new_routed=state['new_routed'],
        feasible=state['feasible'],frontiers=state['frontiers'],points=snapshots,history=state['history'])
    write_json(out/(prefix+'.json'),snapshot)
    text=(root/'summary.md').read_text().replace('(points.csv)',f'({prefix}.csv)').replace('(results.json)',f'({prefix}.json)').replace('(frontier.svg)',f'({prefix}.svg)')
    text=text.replace('| Interval |','| Interval (cycles) |')
    text+='\nPareto membership is computed within this five-design measured pool.\n'
    text+=f'\n[PNG]({prefix}.png) · [SVG]({prefix}.svg)\n'
    (out/(prefix+'.md')).write_text(text)
    print(f'Published {len(valid)} timing-qualified designs and {len(state["frontiers"]["full-ternary"])} Pareto points.')


if __name__=='__main__':main()
