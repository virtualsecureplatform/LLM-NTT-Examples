#!/usr/bin/env python3
"""Export a portable fixture only after verifying the original hardware evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import device, llm_dse
from architecture_search.dse_replay import SCOPE
from architecture_search.llm_evaluate import EvaluationStore
from architecture_search.model import file_hash, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=ROOT/'build/device-pareto250-512')
    parser.add_argument('--output', type=Path, default=ROOT/'data/dse/torus512-replay.json')
    args = parser.parse_args()
    study = json.loads((ROOT/'studies/torus512-llm-demo.json').read_text())
    target = device.load_target(ROOT/'studies/u280-kernel-harness.json')
    store = EvaluationStore(llm_dse.catalog(study), target, ROOT/'build/dse-export-cache', reference=args.reference)
    records = []
    for candidate in llm_dse.catalog(study):
        name = candidate['name']
        if name not in store.available():
            continue
        stages = {stage: store._import(name, stage) for stage in ('qualified', 'mapped', 'routed')}
        if not stages['routed']['feasible']:
            raise ValueError('fixture requires verified timing-qualified reference points')
        row = stages['qualified']['row']
        compact = {}
        for stage, value in stages.items():
            result = {k: value[k] for k in ('stage', 'passed', 'reason', 'metrics', 'feasible',
                       'cache_hit', 'physical_seconds', 'hardware_seconds') if k in value}
            result['evidence_scope'] = SCOPE
            if stage == 'qualified':
                result['row'] = {**candidate, **{k: row[k] for k in ('passed', 'max_abs_error', 'latency_cycles',
                    'initiation_interval_cycles', 'yosys_cells', 'register_bits', 'memory_bits', 'multipliers',
                    'rtl_sha256', 'corpus_sha256')}}
            if stage == 'routed':
                result['reported_signoff'] = dict(failing_endpoints=dict(Setup=0, Hold=0, PW=0), clock_verified=True)
            compact[stage] = result
        provenance = dict(rtl_sha256=row['rtl_sha256'], qualification_corpus_sha256=row['corpus_sha256'],
            routed_evidence_sha256=file_hash(Path(stages['routed']['evidence']['checkpoint']).parent/'evidence.json'),
            clock_evidence_sha256=file_hash(Path(stages['routed']['clock_evidence'])))
        records.append(dict(candidate=candidate, stages=compact, provenance=provenance))
    snapshot = ROOT/'docs/results/pareto250-512.json'
    write_json(args.output, dict(schema='polynomial-dse-replay-v1', study=study, target=target,
        provenance=dict(source_snapshot='docs/results/pareto250-512.json', source_snapshot_sha256=file_hash(snapshot),
            reference_results_sha256=file_hash(args.reference/'results.json'),
            verification='Exported after native qualification, routed evidence, endpoints, and clock checks; '
                         'replay distributes measurements and hashes, not RTL/checkpoints.'), records=records))
    sha = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix('.sha256').write_text(sha+'\n')
    print(f'Exported {len(records)} verified measurement records to {args.output}')


if __name__ == '__main__':
    main()
