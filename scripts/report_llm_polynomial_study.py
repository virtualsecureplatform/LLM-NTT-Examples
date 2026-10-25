#!/usr/bin/env python3
"""Publish compact snapshots after rechecking a completed adaptive comparison."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import llm_dse
from architecture_search.llm_evaluate import EvaluationStore
from architecture_search.model import digest, file_hash, write_json
from scripts.llm_polynomial_study import plot, report


def publish(campaign, output, prefix):
    if not prefix or Path(prefix).name != prefix:
        raise ValueError('prefix must be a filename component')
    campaign, output = Path(campaign).resolve(), Path(output)
    comparison = json.loads((campaign/'comparison.json').read_text())
    states = []
    for run in comparison['runs']:
        path = Path(run['results'])
        state = json.loads(path.read_text())
        if path.parent != campaign/state['policy'] or file_hash(path) != run['results_sha256']:
            raise ValueError('comparison state changed')
        manifest = json.loads((path.parent/'manifest.json').read_text())
        if manifest != run['manifest'] or state['status'] != 'complete' or state['active']:
            raise ValueError('publication requires unchanged completed runs')
        if manifest['controller_sha256'] != file_hash(ROOT/'architecture_search/llm_dse.py'):
            raise ValueError('controller source differs')
        context = manifest['backend']['context']
        if context['evaluator_sha256'] != file_hash(ROOT/'architecture_search/llm_evaluate.py') \
                or any(file_hash(ROOT/p) != sha for p, sha in context['hardware_sources'].items()):
            raise ValueError('evaluator or hardware sources differ')
        for transcript, sha in run['transcripts'].items():
            if file_hash(campaign/transcript) != sha:
                raise ValueError('LLM transcript changed')
        # Validation uses the run's sealed target/tool, without launching Vivado.
        store = EvaluationStore.__new__(EvaluationStore)
        store.rows = {name: stages['qualified']['row'] for name, stages in state['observations'].items()
                      if stages.get('qualified', {}).get('passed')}
        for name, stages in state['observations'].items():
            if name not in store.rows:
                store.rows[name] = dict(configuration={}, workload={}, quant_bits=0)
        store.target, store.tool = manifest['target'], context['tool']
        store.validate_observations(state['observations'])
        measured = llm_dse.progress(state, store.target)
        saved = dict(state['progress'])
        measured['frontier'] = sorted(measured['frontier'])
        saved['frontier'] = sorted(saved['frontier'])
        if saved != measured:
            raise ValueError('stored frontier progress differs from verified evidence')
        if state['seed_name'] != 'full-ternary-2be26723e0be400f':
            raise ValueError('comparison seed differs')
        states.append(state)
    if len({digest(r['manifest']['target']) for r in comparison['runs']}) != 1:
        raise ValueError('comparison mixes targets')
    report(campaign, states, comparison['target'], comparison['mode'])
    plot(campaign, states, comparison['target'])
    snapshot = json.loads((campaign/'comparison.json').read_text())
    snapshot['coverage'] = dict(
        unique_acquired_candidates=len({n for s in states for n in s['observations']}),
        unique_routed_candidates=len({n for s in states for n, v in s['observations'].items() if 'routed' in v}),
        new_physical_qualifications=sum(s['physical_qualified'] for s in snapshot['policies']),
        new_physical_mappings=sum(s['physical_mapped'] for s in snapshot['policies']),
        new_physical_routings=sum(s['physical_routed'] for s in snapshot['policies']))
    snapshot['trials'] = []
    for state in states:
        for proposal in state['proposals']:
            name = proposal['candidate_id']
            stages = state['observations'].get(name, {})
            row = stages.get('qualified', {}).get('row', {})
            snapshot['trials'].append(dict(policy=state['policy'], candidate_id=name, proposal=proposal,
                configuration=row.get('configuration'),
                qualification={k: row[k] for k in ('rtl_sha256', 'corpus_sha256', 'max_abs_error',
                    'latency_cycles', 'initiation_interval_cycles') if k in row},
                stages={stage: {k: value[k] for k in ('passed', 'reason', 'metrics', 'feasible',
                    'cache_hit', 'physical_seconds', 'hardware_seconds') if k in value}
                    for stage, value in stages.items()}))
    write_json(campaign/'comparison.json', snapshot)
    output.mkdir(parents=True, exist_ok=True)
    for source, suffix in [('comparison.json', '.json'), ('comparison.csv', '.csv'),
                           ('points.csv', '-points.csv'), ('comparison.svg', '.svg'), ('comparison.png', '.png')]:
        shutil.copyfile(campaign/source, output/(prefix+suffix))
    text = (campaign/'summary.md').read_text()
    for source, dest in [('comparison.csv', prefix+'.csv'), ('points.csv', prefix+'-points.csv'),
                         ('comparison.json', prefix+'.json'), ('comparison.svg', prefix+'.svg')]:
        text = text.replace('('+source+')', '('+dest+')')
    coverage = snapshot['coverage']
    text += (f"\nAcross policies: {coverage['unique_acquired_candidates']} distinct candidates acquired "
        f"(including the common seed), {coverage['unique_routed_candidates']} distinct candidates routed. "
        f"New physical work: {coverage['new_physical_qualifications']} qualifications, "
        f"{coverage['new_physical_mappings']} mappings, and {coverage['new_physical_routings']} routings.\n")
    text += f'\n[PNG]({prefix}.png) · [SVG]({prefix}.svg)\n'
    (output/(prefix+'.md')).write_text(text)
    print(f'Published {comparison["mode"]} comparison: {len(states)} completed policies.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT/'docs/results')
    p.add_argument('--prefix', default='llm-dse-512')
    args = p.parse_args()
    publish(args.campaign, args.output_dir, args.prefix)


if __name__ == '__main__':
    main()
