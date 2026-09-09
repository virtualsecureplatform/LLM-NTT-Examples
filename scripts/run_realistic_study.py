#!/usr/bin/env python3
"""Prepare, run and audit the frozen realistic NTT policy study (no reference pool)."""
import argparse
import copy
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import build_identity, constraints, hardware
from architecture_search.model import (canonical, evidence_integrity, file_hash,
                                       metric_number, run, source_identity, write_json)

POLICIES = ['enumerate', 'random', 'cost', 'llm']
CAPS = {'lut': 50000, 'ff': 100000, 'dsp': 512, 'bram': 512, 'uram': 64}
DEVELOPMENT = ['fhe4k32', 'fhe4k60'] + ['ckks8k-prime' + str(i) for i in range(4)]
HELD_OUT = ['fhe16k54', 'fhe64k54']


def read(path):
    return json.loads(Path(path).read_text())


def now():
    return datetime.now(timezone.utc).isoformat()


def executable_inputs(ngen):
    paths = list((ROOT / 'architecture_search').glob('*.py'))
    paths += [ROOT / 'scripts' / name for name in (
        'run_realistic_study.py', 'run_live_policy_trials.py', 'search_architectures.py',
        'vitis_synth_rtl.sh', 'insert_output_hold_buffers.tcl', 'insert_input_hold_buffers.tcl')]
    paths += [ngen / 'ngen.bat']
    paths += list((ngen / 'scripts').glob('*.py'))
    return {str(p): file_hash(p) for p in sorted(paths)}


def prepare(out, ngen):
    if out.exists() and any(out.iterdir()):
        raise ValueError('Preparation requires an empty output directory')
    identity = build_identity.verify(ngen)
    if not identity['verified']:
        raise ValueError('NGen assembly does not match checkout: ' + canonical(identity))
    cases = []
    for split, names in [('development', DEVELOPMENT), ('held-out', HELD_OUT)]:
        for name in names:
            for direction in ('forward', 'inverse'):
                case = name + '-' + direction
                c = read(ROOT / 'campaigns/realistic-v1/search' / (case + '.json'))
                c['resource_limits'] = CAPS
                c['bandwidth'] = {'shared_bits_per_second': 64000000000, 'coefficient_bits': 64}
                c['budget'] = {'hours': 2, 'functional': 3, 'synthesis': 3, 'route': 0}
                c['llm'] = {'endpoint': 'http://kunashiri.sato.lab:8080/v1',
                            'model': 'unsloth/Qwen3.8-Flash-Next-GGUF:UD-IQ4_XS'}
                path = out / 'campaigns' / (case + '.json')
                write_json(path, c)
                cases.append({'name': case, 'split': split, 'campaign': str(path),
                              'sha256': file_hash(path)})
    protocol = {
        'schema': 'ntt-realistic-policy-study-v1', 'created_utc': now(),
        'framework': source_identity(ROOT), 'ngen': source_identity(ngen),
        'ngen_root': str(ngen), 'ngen_build': identity,
        'inputs': executable_inputs(ngen), 'cases': cases,
        'policies': POLICIES, 'seed': 2, 'evaluations_per_trial': 3, 'hours_per_trial': 2,
        'route_hours_per_candidate': 3,
        'route_selection': 'Forward only: fastest bandwidth-capped feasible synthesis, then lowest LUT; ties use configuration then policy; deduplicate configurations. Freeze selections before routing.',
        'order': 'Development trials, development routes, held-out freeze marker, held-out trials, held-out routes. Rotate policy order by case index.',
        'limitations': ['One repetition per policy; no statistical superiority claim.',
                       'No complete reference pool: no frontier recall.',
                       '8 GB/s aggregate transfer rate is a declared service model, not measured board bandwidth.',
                       'OOC U280 fabric at 4 ns; synthesis feasibility does not establish routed timing closure.',
                       'Queue time consumes each trial budget; unrelated vendor jobs can confound wall time.',
                       'Held-out workloads have prior functional validation; policy receives no cross-trial measurements.']}
    write_json(out / 'protocol.json', protocol)
    (out / 'protocol.sha256').write_text(file_hash(out / 'protocol.json') + '\n')
    return protocol


def guard(out, p):
    if file_hash(out / 'protocol.json') != (out / 'protocol.sha256').read_text().strip():
        raise ValueError('Frozen protocol changed')
    if executable_inputs(Path(p['ngen_root'])) != p['inputs']:
        raise ValueError('Frozen executable inputs changed')
    if not build_identity.verify(Path(p['ngen_root']))['verified']:
        raise ValueError('Frozen NGen sources no longer match assembly')
    for case in p['cases']:
        if file_hash(Path(case['campaign'])) != case['sha256']:
            raise ValueError('Frozen campaign changed: ' + case['name'])


def eligible(record, campaign, stage='synthesis'):
    e = record.get('evidence', {}).get(stage, {})
    m = e.get('metrics', {})
    if record.get('correct') is not True or record.get('mode') != 'functional':
        return False
    if (e.get('passed') is not True or e.get('implementation_passed') is not True
            or e.get('target') != campaign['target']):
        return False
    if not metric_number(m.get('wns_ns')) or m['wns_ns'] < 0:
        return False
    if stage == 'route' and (not metric_number(m.get('hold_slack_ns')) or m['hold_slack_ns'] < 0):
        return False
    if evidence_integrity(e) != 'verified':
        return False
    rtl = Path(record.get('rtl_path', ''))
    if not rtl.is_file() or file_hash(rtl) != record.get('rtl_hash'):
        return False
    if any(not metric_number(m.get(k)) or m[k] < 0 or m[k] > cap
           for k, cap in campaign['resource_limits'].items()):
        return False
    return (metric_number(m.get('transforms_per_second')) and m['transforms_per_second'] > 0
            and metric_number(m.get('latency_ns')) and m['latency_ns'] > 0)


def rate(record, campaign, stage='synthesis'):
    measured = record['evidence'][stage]['metrics']['transforms_per_second']
    bound = constraints.bandwidth_bound(campaign['workload'], campaign['bandwidth'])
    return min(measured, bound['upper_transforms_per_second'])


def select_routes(rows, campaign):
    if campaign['workload']['direction'] != 'forward':
        return []
    qualified = [r for r in rows if eligible(r['record'], campaign)]
    if not qualified:
        return []
    def tie(row):
        return canonical(row['record']['configuration']), row['policy']
    fastest = min(qualified, key=lambda r: (-rate(r['record'], campaign), *tie(r)))
    smallest = min(qualified, key=lambda r: (r['record']['evidence']['synthesis']['metrics']['lut'], *tie(r)))
    result = []
    for why, row in [('fastest', fastest), ('lowest_lut', smallest)]:
        key = canonical(row['record']['configuration'])
        previous = next((r for r in result if canonical(r['record']['configuration']) == key), None)
        if previous:
            previous['reasons'].append(why)
        else:
            result.append({**row, 'reasons': [why]})
    return result


def trial_rows(out, case, method, p):
    directory = out / 'trials' / case['name'] / method
    manifest = directory / 'manifest.json'
    if not manifest.exists():
        return []
    m = read(manifest)
    if (m['campaign'] != read(case['campaign']) or m['policies'] != [method]
            or m['seeds'] != [p['seed']] or m['evaluations_per_trial'] != p['evaluations_per_trial']
            or m['hours_total'] != p['hours_per_trial'] or m['inputs'].get(str(Path(p['ngen_root']) / 'ngen.bat')) != p['ngen_build']['binary_sha256']):
        raise ValueError('Unmatched trial inputs or budget: ' + str(directory))
    for path, digest in m['inputs'].items():
        if p['inputs'].get(path) != digest:
            raise ValueError('Trial executable identity differs from protocol: ' + path)
    paths = sorted((directory / (method + '-' + str(p['seed'])) / 'candidates').glob('*/record.json'))
    return [{'policy': method, 'source_record': str(path), 'record': read(path)} for path in paths]


def summarize(out, p):
    trials = []
    state = read(out / 'state.json') if (out / 'state.json').exists() else {'completed': {}}
    for case in p['cases']:
        c = read(case['campaign'])
        for method in p['policies']:
            directory = out / 'trials' / case['name'] / method
            rows = trial_rows(out, case, method, p)
            feasible = [r for r in rows if eligible(r['record'], c)]
            result = read(directory / 'results.json') if (directory / 'results.json').exists() else {}
            trial = result.get('trials', [{}])[0]
            attempt = state['completed'].get('trial/' + case['name'] + '/' + method)
            queue = [r['record'].get('evidence', {}).get('synthesis', {}).get('queue_seconds') for r in rows]
            failures = []
            for row in rows:
                record = row['record']; e = record.get('evidence', {}).get('synthesis', {})
                if record.get('correct') is not True:
                    category = 'functional_or_generation_failure'
                elif 'queue timeout' in e.get('error', '').lower():
                    category = 'queue_timeout'
                elif e.get('process', {}).get('timed_out'):
                    category = 'execution_timeout'
                elif e.get('implementation_passed') is not True:
                    category = 'implementation_missing_or_failed'
                elif e.get('passed') is not True:
                    category = 'timing_failure'
                elif not eligible(record, c):
                    category = 'resource_or_integrity_ineligible'
                else:
                    continue
                failures.append({'id': record['id'], 'category': category})
            trials.append({'case': case['name'], 'split': case['split'], 'policy': method,
                           'requested_evaluations': p['evaluations_per_trial'],
                           'evaluations_completed': trial.get('evaluations_completed', len(rows)),
                           'terminal': bool(result) or attempt is not None,
                           'stop_reason': trial.get('stop_reason') if result else ('Runner ended without results.json' if attempt else None),
                           'runner_process': attempt.get('process') if attempt else None,
                           'elapsed_seconds': trial.get('elapsed_seconds'),
                           'known_queue_seconds': sum(v for v in queue if metric_number(v)),
                           'unknown_queue_records': sum(not metric_number(v) for v in queue),
                           'feasible_discoveries': len(feasible), 'failures': failures,
                           'best_bandwidth_capped_transforms_per_second': max((rate(r['record'], c) for r in feasible), default=None),
                           'feasible_candidates': [{'id': r['record']['id'], 'configuration': r['record']['configuration'],
                                                    'metrics': r['record']['evidence']['synthesis']['metrics'],
                                                    'bandwidth_capped_transforms_per_second': rate(r['record'], c)} for r in feasible]})
    routes = []
    for path in sorted((out / 'routes').glob('*/*/record.json')):
        record = read(path)
        case = next(c for c in p['cases'] if c['name'] == path.parent.parent.name)
        campaign = read(case['campaign'])
        routes.append({'case': case['name'], 'record': str(path), 'id': record['id'],
                       'route_feasible': eligible(record, campaign, 'route'),
                       'metrics': record['evidence']['route'].get('metrics', {}),
                       'queue_seconds': record['evidence']['route'].get('queue_seconds')})
    result = {'schema': 'ntt-realistic-policy-summary-v1', 'updated_utc': now(),
              'protocol_sha256': file_hash(out / 'protocol.json'),
              'trials': trials, 'routes': routes, 'limitations': p['limitations'],
              'terminal_trials': sum(t['terminal'] for t in trials), 'requested_trials': len(trials),
              'evaluations_completed': sum(t['evaluations_completed'] for t in trials),
              'requested_evaluations': len(trials) * p['evaluations_per_trial']}
    write_json(out / 'summary.json', result)
    return result


def execute(out, p):
    # A second orchestrator must never duplicate live measurements.
    with (out / 'orchestrator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard(out, p)
        statepath = out / 'state.json'
        state = read(statepath) if statepath.exists() else {'completed': {}, 'active': None}
        if state['active']:
            raise ValueError('Interrupted work requires inspection; refusing to overwrite: ' + canonical(state['active']))
        def begin(key):
            guard(out, p)
            state['active'] = {'key': key, 'started_utc': now()}
            write_json(statepath, state)
            print(now(), key, flush=True)
        def finish(key, result):
            state['completed'][key] = {'finished_utc': now(), **result}
            state['active'] = None
            write_json(statepath, state)
            summarize(out, p)
        for split in ('development', 'held-out'):
            if split == 'held-out':
                marker = out / 'held-out-freeze.json'
                if not marker.exists():
                    write_json(out / 'development-summary.json', read(out / 'summary.json'))
                    write_json(marker, {'created_utc': now(), 'protocol_sha256': file_hash(out / 'protocol.json'),
                                        'development_summary_sha256': file_hash(out / 'development-summary.json'),
                                        'completed_work': copy.deepcopy(state['completed']),
                                        'policy_changed_after_development': False})
            cases = [c for c in p['cases'] if c['split'] == split]
            for index, case in enumerate(cases):
                order = p['policies'][index % 4:] + p['policies'][:index % 4]
                for method in order:
                    key = 'trial/' + case['name'] + '/' + method
                    if key in state['completed']:
                        continue
                    directory = out / 'trials' / case['name'] / method
                    if directory.exists():
                        raise ValueError('Existing uncheckpointed trial: ' + str(directory))
                    begin(key)
                    process = run([sys.executable, str(ROOT / 'scripts/run_live_policy_trials.py'),
                                   '--campaign', case['campaign'], '--output-dir', str(directory),
                                   '--policies', method, '--seeds', str(p['seed']),
                                   '--evaluations', str(p['evaluations_per_trial']),
                                   '--hours', str(p['hours_per_trial']), '--ngen-root', p['ngen_root']],
                                  ROOT, out / 'logs' / (case['name'] + '-' + method + '.log'),
                                  p['hours_per_trial'] * 3600 + 60)
                    finish(key, {'process': process})
            selection_path = out / (split + '-route-selection.json')
            if not selection_path.exists():
                selections = []
                for case in cases:
                    rows = [row for method in p['policies'] for row in trial_rows(out, case, method, p)]
                    for row in select_routes(rows, read(case['campaign'])):
                        selections.append({'case': case['name'], **row,
                                           'source_record_sha256': file_hash(Path(row['source_record']))})
                write_json(selection_path, {'created_utc': now(), 'selections': selections,
                                            'rule': p['route_selection']})
            for selected in read(selection_path)['selections']:
                case = next(c for c in cases if c['name'] == selected['case'])
                campaign = read(case['campaign'])
                record = copy.deepcopy(selected['record'])
                key = 'route/' + case['name'] + '/' + record['id']
                if key in state['completed']:
                    continue
                if (file_hash(Path(selected['source_record'])) != selected['source_record_sha256']
                        or not eligible(record, campaign)):
                    raise ValueError('Selected synthesis evidence changed')
                begin(key)
                directory = out / 'routes' / case['name'] / record['id']
                try:
                    record['evidence']['route'] = hardware.evaluate(
                        Path(record['rtl_path']), 'SearchTop', campaign['target'], record['evaluation']['metrics'],
                        directory / 'route', 'route', p['route_hours_per_candidate'] * 3600)
                except (OSError, ValueError, KeyError) as error:
                    record['evidence']['route'] = {'passed': False, 'error': str(error)}
                record['status'] = 'complete' if record['evidence']['route']['passed'] else 'hardware_failed'
                record['study_selection'] = {k: v for k, v in selected.items() if k != 'record'}
                write_json(directory / 'record.json', record)
                finish(key, {'passed': record['evidence']['route']['passed'], 'record': str(directory / 'record.json')})
        guard(out, p)
        write_json(out / 'final-summary.json', read(out / 'summary.json'))
        write_json(out / 'complete.json', {'finished_utc': now(), 'summary_sha256': file_hash(out / 'final-summary.json'),
                                         'meaning': 'All scheduled attempts terminal; inspect failures and incomplete budgets in summary.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'summarize'])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--ngen-root', type=Path, default=ROOT.parent / 'NGen')
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if args.action == 'prepare':
        prepare(out, args.ngen_root.resolve())
    else:
        p = read(out / 'protocol.json')
        guard(out, p)
        if args.action == 'run':
            execute(out, p)
        else:
            result = summarize(out, p)
            print(canonical({k: result[k] for k in ('terminal_trials', 'requested_trials', 'evaluations_completed', 'requested_evaluations')}))


if __name__ == '__main__':
    main()
