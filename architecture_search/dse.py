"""One experiment interface: python3 -m architecture_search.dse --help."""
import argparse
import contextlib
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from . import device, llm_dse
from .dse_replay import BUNDLE, ExplainedStore, PortableReplayStore, failure_reason
from .model import digest, file_hash, write_json

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ('llm', 'random', 'analytical')
SCHEMA = 'polynomial-dse-experiment-v1'


def template(path, mode='replay', with_llm=False):
    return dict(schema=SCHEMA, mode=mode,
        study=json.loads((ROOT/'studies/torus512-llm-demo.json').read_text()),
        target=json.loads((ROOT/'studies/u280-kernel-harness.json').read_text()),
        policies=list(POLICIES) if with_llm else ['random', 'analytical'], seed=1,
        budgets=dict(candidates=4, routes=2, timeout_seconds=3600, threads=4),
        llm=dict(base_url=llm_dse.BASE_URL, model=llm_dse.MODEL),
        replay_dataset='bundled:torus512', output_dir='build/dse/'+Path(path).stem,
        live=dict(reference='repo:build/device-pareto250-512', cache='repo:build/llm-dse-cache',
                  vivado='/home/opt/xilinx/Vivado/2023.2/bin/vivado'))


def require_fields(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(label+' must be a JSON object')
    if set(value) != set(expected):
        missing, unknown = sorted(set(expected)-set(value)), sorted(set(value)-set(expected))
        raise ValueError(f'{label}: missing fields {missing}; unknown fields {unknown}. '
                         'API keys belong in LLM_DSE_API_KEY, not JSON.')


def load_config(path):
    value = json.loads(Path(path).read_text())
    require_fields(value, ('schema', 'mode', 'study', 'target', 'policies', 'seed', 'budgets',
                          'llm', 'replay_dataset', 'output_dir', 'live'), 'experiment')
    if value['schema'] != SCHEMA or value['mode'] not in ('replay', 'live'):
        raise ValueError('expected polynomial-dse-experiment-v1 in replay or live mode')
    policies = value['policies']
    if not isinstance(policies, list) or not policies or any(p not in POLICIES for p in policies) \
            or len(set(policies)) != len(policies):
        raise ValueError('policies must be a unique nonempty list of llm, random, analytical')
    if type(value['seed']) is not int:
        raise ValueError('seed must be an integer')
    require_fields(value['budgets'], ('candidates', 'routes', 'timeout_seconds', 'threads'), 'budgets')
    b = value['budgets']
    if any(type(v) is not int for v in b.values()) or b['candidates'] < 1 \
            or not 0 <= b['routes'] <= b['candidates']//2 or b['timeout_seconds'] < 1 \
            or not 1 <= b['threads'] <= 32:
        raise ValueError('invalid budgets: candidates >= 1, routes <= candidates/2, timeout > 0, threads 1..32')
    require_fields(value['llm'], ('base_url', 'model'), 'llm')
    llm = value['llm']
    if not isinstance(llm['base_url'], str) or not isinstance(llm['model'], str) or not llm['model'].strip():
        raise ValueError('LLM base_url and model must be nonempty strings')
    url = urllib.parse.urlsplit(llm['base_url'])
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('LLM URL must be an http(s) base URL without credentials, query, or fragment')
    require_fields(value['live'], ('reference', 'cache', 'vivado'), 'live')
    for text in (value['replay_dataset'], value['output_dir'], *value['live'].values()):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('dataset, output, and live paths must be nonempty strings')
    if not isinstance(value['study'], dict) or not isinstance(value['target'], dict) \
            or not isinstance(value['target'].get('capacity'), dict):
        raise ValueError('study, target, and target.capacity must be JSON objects')
    llm_dse.seed_name(llm_dse.catalog(value['study']))
    # Reuse target validation without changing the historical device module.
    with tempfile.TemporaryDirectory() as directory:
        target_file = Path(directory)/'target.json'
        write_json(target_file, value['target'])
        target = device.load_target(target_file)
    if target['clock_mhz'] != 250 or target['implementation_context'] != 'registered-harness-v2' \
            or target['implementation_directive'] != 'Default':
        raise ValueError('this version supports the Default 250 MHz registered-harness-v2 target')
    return value


def resolve(path, text):
    if text == 'bundled:torus512':
        return BUNDLE
    if text.startswith('repo:'):
        return ROOT/text[5:]
    candidate = Path(text).expanduser()
    return candidate if candidate.is_absolute() else Path(path).resolve().parent/candidate


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class Client(llm_dse.LLMClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def redact(self, value):
        if isinstance(value, dict):
            return {self.redact(k): self.redact(v) for k, v in value.items()}
        return super().redact(value)


def endpoint_check(config):
    key = os.environ.get('LLM_DSE_API_KEY', '')
    if not key:
        raise ValueError('set LLM_DSE_API_KEY to use the LLM policy')
    request = urllib.request.Request(config['llm']['base_url'].rstrip('/')+'/models',
                                     headers={'Authorization': 'Bearer '+key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            data = json.load(response)
        models = [m['id'] for m in data['data'] if isinstance(m.get('id'), str)]
        if config['llm']['model'] not in models:
            raise ValueError('configured model is absent from endpoint /models')
    except urllib.error.HTTPError as error:
        raise ValueError(f'endpoint returned HTTP {error.code}; check URL and LLM_DSE_API_KEY') from None
    except (OSError, KeyError, TypeError):
        raise ValueError('endpoint /models is unreachable or returned an invalid response') from None
    return 'endpoint reachable; configured model is available'


def _portable(config, path):
    rows = llm_dse.catalog(config['study'])
    return PortableReplayStore(resolve(path, config['replay_dataset']), rows, config['target'])


def preflight(config, path, check_llm=True):
    checks = []
    def check(name, function):
        try:
            detail = function()
            checks.append(dict(name=name, ok=True, detail=detail))
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
            key = os.environ.get('LLM_DSE_API_KEY')
            detail = str(error).replace(key, '[REDACTED]') if key else str(error)
            checks.append(dict(name=name, ok=False, detail=detail))
    if config['mode'] == 'replay':
        def fixture():
            store = _portable(config, path)
            if config['budgets']['candidates'] > len(store.rows)-1:
                raise ValueError(f"candidate budget exceeds the closed replay pool ({len(store.rows)-1} new candidates)")
            return f'{len(store.rows)} checksummed measurement records; FPGA tools are not required'
        check('replay dataset', fixture)
    else:
        from . import build_identity
        from .paths import NGEN
        def program(name):
            if not shutil.which(name):
                raise ValueError('install '+name+' before running live evaluation')
            return shutil.which(name)
        check('Apptainer', lambda: program('apptainer'))
        def generator():
            if not build_identity.verify(NGEN)['verified']:
                raise ValueError('NGen assembly is missing/stale; run scripts/build_generators.sh')
            return 'NGen assembly matches current generator sources'
        check('generator', generator)
        image = ROOT/'build/fhe512-sgen-precision.sif'
        def image_check():
            if not image.is_file():
                raise ValueError('pinned image missing; run scripts/build_fhe512_image.sh')
            if not (ROOT/'build/tools/bin/yosys').is_file():
                raise ValueError('Yosys missing; run scripts/build_assurance_yosys.sh')
            env = dict(os.environ)
            env.pop('LLM_DSE_API_KEY', None)
            probe = subprocess.run(['apptainer', 'exec', '--cleanenv', '--no-home', '--bind', f'{ROOT}:{ROOT}',
                str(image), 'sh', '-c', 'command -v java && test -x /usr/local/lib/python3.10/dist-packages/verilator/bin/verilator'],
                env=env, capture_output=True, timeout=30)
            if probe.returncode:
                raise ValueError('pinned container lacks Java or Verilator; rebuild the image')
            return 'pinned image, Yosys, Java, and Verilator are present'
        check('simulator and synthesis tools', image_check)
        if all(c['ok'] for c in checks):
            def reference():
                from .llm_evaluate import EvaluationStore
                if not tool_path(config['live']['vivado'], path).is_file():
                    raise ValueError('Vivado executable missing; set live.vivado to the Vivado 2023.2 executable')
                if not (resolve(path, config['live']['reference'])/'results.json').is_file():
                    raise ValueError('seed reference missing; set live.reference to a completed v2 campaign '
                                     '(docs/device-polynomial-search.md)')
                with without_api_key(), tempfile.TemporaryDirectory() as directory:
                    store = EvaluationStore(llm_dse.catalog(config['study']), config['target'], directory,
                        mode='live', reference=resolve(path, config['live']['reference']),
                        timeout=config['budgets']['timeout_seconds'], threads=config['budgets']['threads'],
                        vivado=tool_path(config['live']['vivado'], path))
                    store.seed(llm_dse.seed_name(llm_dse.catalog(config['study'])))
                return 'Vivado identity and reusable seed qualification/routed evidence verified'
            check('Vivado and seed evidence', reference)
        else:
            checks.append(dict(name='Vivado and seed evidence', ok=False,
                               detail='resolve the toolchain prerequisites, then rerun preflight'))
    if 'llm' in config['policies'] and check_llm:
        check('LLM endpoint', lambda: endpoint_check(config))
    else:
        checks.append(dict(name='LLM endpoint', ok=True, detail='not needed for these pending policies'))
    if config['budgets']['candidates'] > len(llm_dse.catalog(config['study']))-1:
        checks.append(dict(name='candidate budget', ok=False, detail='candidate budget exceeds the legal search pool'))
    return dict(ok=all(c['ok'] for c in checks), mode=config['mode'], checks=checks)


def tool_path(text, path):
    return Path(shutil.which(text) or resolve(path, text))


@contextlib.contextmanager
def without_api_key():
    key = os.environ.pop('LLM_DSE_API_KEY', None)
    try:
        yield
    finally:
        if key is not None:
            os.environ['LLM_DSE_API_KEY'] = key


@contextlib.contextmanager
def lock_output(out):
    out.mkdir(parents=True, exist_ok=True)
    with (out/'.lock').open('w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('experiment is running; use status to inspect it') from None
        yield


def metadata(config):
    return dict(schema='polynomial-dse-run-v1', config=config, config_sha256=digest(config),
        interface_sources={p.name: file_hash(p) for p in [Path(__file__),
            ROOT/'architecture_search/dse_replay.py', ROOT/'architecture_search/dse_report.py']})


def check_metadata(out, config):
    saved = json.loads((out/'experiment.json').read_text())
    if saved != metadata(config):
        raise ValueError('experiment configuration or interface source changed; restore it or choose a new output_dir')
    return saved


def read_states(out, policies):
    return [json.loads((out/p/'results.json').read_text()) for p in policies if (out/p/'results.json').exists()]


def validate_states(states, config, path):
    if config['mode'] == 'replay':
        store = _portable(config, path)
    else:
        from .llm_evaluate import EvaluationStore
        store = EvaluationStore.__new__(EvaluationStore)
        store.rows = {r['name']: r for r in llm_dse.catalog(config['study'])}
        store.target = config['target']
        store.tool = None
    for state in states:
        if config['mode'] == 'live':
            out = resolve(path, config['output_dir'])
            manifest = json.loads((out/state['policy']/'manifest.json').read_text())
            store.tool = manifest['backend']['context']['tool']
        store.validate_observations(state['observations'])


def make_report(config, path, out):
    from .dse_report import generate
    saved = check_metadata(out, config)
    states = read_states(out, config['policies'])
    validate_states(states, config, path)
    return generate(out, states, config['target'], config['mode'], saved)


def run_experiment(config, path):
    out = resolve(path, config['output_dir'])
    with lock_output(out):
        if (out/'experiment.json').exists():
            check_metadata(out, config)
        elif any(out.glob('*/results.json')):
            raise ValueError('output contains another campaign; choose a new output_dir')
        existing = {s['policy']: s for s in read_states(out, config['policies'])}
        all_done = len(existing) == len(config['policies']) and all(s['status']=='complete' for s in existing.values())
        if all_done:
            make_report(config, path, out)
            print('Already complete; verified records and refreshed reports without evaluations.')
            return 0
        pending_llm = 'llm' in config['policies'] and existing.get('llm', {}).get('status') != 'complete'
        health = preflight(config, path, check_llm=pending_llm)
        print_checks(health)
        if not health['ok']:
            return 2
        client = Client(**config['llm']) if pending_llm else None
        with without_api_key():
            if config['mode'] == 'replay':
                store = _portable(config, path)
                rows = store.rows
            else:
                from .llm_evaluate import EvaluationStore
                rows = llm_dse.catalog(config['study'])
                native = EvaluationStore(rows, config['target'], resolve(path, config['live']['cache']), mode='live',
                    reference=resolve(path, config['live']['reference']), timeout=config['budgets']['timeout_seconds'],
                    threads=config['budgets']['threads'], vivado=tool_path(config['live']['vivado'], path))
                store = ExplainedStore(native, config['target'])
            write_json(out/'experiment.json', metadata(config))
            for policy in config['policies']:
                try:
                    llm_dse.run_search(rows, config['target'], store, out/policy, policy=policy,
                        seed=config['seed'], max_candidates=config['budgets']['candidates'],
                        route_budget=config['budgets']['routes'], client=client,
                        resume=(out/policy/'manifest.json').exists(),
                        settings=config['llm'] if policy == 'llm' else {})
                except llm_dse.LLMAuthenticationError:
                    raise
                except llm_dse.LLMError:
                    make_report(config, path, out)
                    continue
                make_report(config, path, out)
            print('Report: '+str(out/'report.html'))
            return 0 if all(s['status']=='complete' for s in read_states(out, config['policies'])) else 1


def status(config, path):
    out = resolve(path, config['output_dir'])
    stored = json.loads((out/'experiment.json').read_text()) if (out/'experiment.json').exists() else None
    effective = stored['config'] if stored else config
    lookup = {r['name']: r['configuration'] for r in llm_dse.catalog(effective['study'])}
    states = {s['policy']: s for s in read_states(out, effective['policies'])}
    items = []
    for policy in effective['policies']:
        s = states.get(policy)
        if s is None:
            items.append(dict(policy=policy, status='not started'))
            continue
        budget = effective['budgets']
        item = dict(policy=policy, status=s['status'], progress=llm_dse.progress(s, effective['target']),
            remaining=dict(candidates=budget['candidates']-len(s['selected']),
                           mappings=budget['candidates']-s['attempts']['mapped'],
                           routes=budget['routes']-s['attempts']['routed']), active=copy.deepcopy(s['active']),
            failures=[dict(candidate_id=n, stage=stage, reason=failure_reason(r, stage, effective['target']))
                for n, stages in s['observations'].items() for stage, r in stages.items()
                if failure_reason(r, stage, effective['target'])], error=s.get('error'))
        if item['active']:
            item['active']['configuration'] = lookup[item['active']['candidate_id']]
        elif s['status'] == 'running':
            selection = out/policy/'llm'/f'selection-{len(s["selected"])+1}'
            calls = sorted(selection.glob('call-*.json'))
            if calls:
                call = json.loads(calls[-1].read_text())
                if 'seconds' not in call:
                    item['active'] = dict(stage='LLM inference', started_at=call['started_at'])
        if item['active']:
            item['active']['elapsed_seconds'] = max(0, time.time()-item['active']['started_at'])
        items.append(item)
    return dict(mode=effective['mode'], output_dir=str(out), config_changed=bool(stored and stored['config'] != config),
                report=str(out/'report.html') if (out/'report.html').exists() else None, policies=items)


def print_checks(health):
    for c in health['checks']:
        print(('OK' if c['ok'] else 'FAIL')+'  '+c['name']+': '+c['detail'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'preflight', 'run', 'status', 'report'):
        p = sub.add_parser(name)
        p.add_argument('experiment', type=Path)
        if name == 'init':
            p.add_argument('--mode', choices=['replay', 'live'], default='replay')
            p.add_argument('--with-llm', action='store_true')
        if name in ('preflight', 'status'):
            p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            args.experiment.parent.mkdir(parents=True, exist_ok=True)
            with args.experiment.open('x') as stream:
                stream.write(json.dumps(template(args.experiment, args.mode, args.with_llm), indent=2)+'\n')
            print('Created '+str(args.experiment)+'. Next: python3 -m architecture_search.dse run '+str(args.experiment))
            return 0
        config = load_config(args.experiment)
        if args.command == 'preflight':
            result = preflight(config, args.experiment)
            print(json.dumps(result, indent=2)) if args.json else print_checks(result)
            return 0 if result['ok'] else 2
        if args.command == 'run':
            return run_experiment(config, args.experiment)
        if args.command == 'report':
            out = resolve(args.experiment, config['output_dir'])
            with lock_output(out):
                make_report(config, args.experiment, out)
            print('Report: '+str(out/'report.html'))
            return 0
        result = status(config, args.experiment)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print('Mode: '+result['mode']+' | Output: '+result['output_dir'])
            if result['config_changed']:
                print('Configuration changed; showing the saved experiment. Restore it or choose a new output_dir to run.')
            for s in result['policies']:
                p = s.get('progress')
                print(s['policy']+': '+s['status']+(f" | candidates {p['candidates']} | maps {p['mapped']} | routes {p['routed']} "
                      f"| feasible {p['feasible']} | best {p['best_products_per_second']:,.1f} modeled products/s" if p else ''))
                if s.get('active'):
                    a = s['active']
                    print(f"  Active: {a['stage']} ({a['elapsed_seconds']:.0f}s) "+str(a.get('configuration', '')))
                if 'remaining' in s:
                    print('  Remaining: '+', '.join(f'{v} {k}' for k, v in s['remaining'].items()))
                for failure in s.get('failures', []):
                    print('  '+failure['candidate_id']+': '+failure['reason'])
                if s.get('error'):
                    print('  Error: '+s['error'])
            if result['report']:
                print('Report: '+result['report'])
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        # Exclude server-provided error bodies and any in-process credential.
        message = str(error)
        key = os.environ.get('LLM_DSE_API_KEY')
        if key:
            message = message.replace(key, '[REDACTED]')
        print('Error: '+message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
