import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from architecture_search import dse, llm_dse
from architecture_search.dse_replay import BUNDLE, PortableReplayStore
from architecture_search.model import file_hash, write_json

ROOT = Path(__file__).resolve().parents[2]


class CLIBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path = self.base/'experiment.json'
        self.config = dse.template(self.path)
        self.config['policies'] = ['random']
        self.config['budgets'].update(candidates=2, routes=1)
        write_json(self.path, self.config)

    def cli(self, *args, env=None, cwd=ROOT):
        process_env = dict(os.environ)
        process_env.pop('LLM_DSE_API_KEY', None)
        process_env.pop('PYTHONPATH', None)
        if env:
            process_env.update(env)
        return subprocess.run([sys.executable, '-S', '-m', 'architecture_search.dse', *map(str, args)],
                              cwd=cwd, env=process_env, capture_output=True, text=True, timeout=90)

    def run_ok(self, *args, **kwargs):
        result = self.cli(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        return result


class CLITests(CLIBase):
    def test_fresh_checkout_offline_workflow_and_relocation(self):
        clean = self.base/'checkout'
        clean.mkdir()
        for folder in ('architecture_search', 'scripts', 'studies', 'data'):
            shutil.copytree(ROOT/folder, clean/folder, ignore=shutil.ignore_patterns('__pycache__'))
        empty_path = self.base/'empty-path'
        empty_path.mkdir()
        env = {'PATH': str(empty_path)}
        self.run_ok('init', 'experiment.json', cwd=clean, env=env)
        before = json.loads(self.run_ok('status', 'experiment.json', '--json', cwd=clean, env=env).stdout)
        self.assertTrue(all(p['status']=='not started' for p in before['policies']))
        self.run_ok('preflight', 'experiment.json', cwd=clean, env=env)
        self.run_ok('run', 'experiment.json', cwd=clean, env=env)
        out = clean/'build/dse/experiment'
        report = json.loads((out/'comparison.json').read_text())
        self.assertEqual([p['status'] for p in report['policies']], ['complete', 'complete'])
        self.assertTrue(all(p['physical_mapped']==0 and p['physical_routed']==0 for p in report['policies']))
        self.assertIn('Published measurement replay', report['evidence_scope'])
        self.assertEqual(len(report['trials']), 8)
        ET.fromstring((out/'comparison.svg').read_text())
        page = (out/'report.html').read_text()
        self.assertIn('<svg', page)
        self.assertNotIn('<script src=', page)
        self.assertTrue((out/'points.csv').is_file())
        hashes = {p.relative_to(clean): file_hash(p) for p in out.glob('*/results.json')}
        moved = self.base/'moved-checkout'
        shutil.move(clean, moved)
        self.run_ok('run', 'experiment.json', cwd=moved, env=env)
        self.run_ok('report', 'experiment.json', cwd=moved, env=env)
        self.assertTrue(all(file_hash(moved/p)==sha for p, sha in hashes.items()))
        self.assertFalse((moved/'third_party').exists())

    def test_config_immutability_and_init_never_overwrites(self):
        self.run_ok('run', self.path)
        out = dse.resolve(self.path, self.config['output_dir'])
        state_path = out/'random/results.json'
        sha = file_hash(state_path)
        self.config['budgets'].update(candidates=4, routes=2)
        write_json(self.path, self.config)
        result = self.cli('run', self.path)
        self.assertEqual(result.returncode, 2)
        self.assertIn('configuration or interface source changed', result.stderr)
        self.assertEqual(file_hash(state_path), sha)
        result = json.loads(self.run_ok('status', self.path, '--json').stdout)
        self.assertTrue(result['config_changed'])
        self.assertEqual(result['policies'][0]['progress']['candidates'], 2)
        before = self.path.read_bytes()
        self.assertEqual(self.cli('init', self.path).returncode, 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_replay_corruption_and_inconsistent_signoff_stop_before_trials(self):
        data_path = self.base/'fixture.json'
        shutil.copyfile(BUNDLE, data_path)
        shutil.copyfile(BUNDLE.with_suffix('.sha256'), data_path.with_suffix('.sha256'))
        self.config['replay_dataset'] = 'fixture.json'
        write_json(self.path, self.config)
        data_path.write_bytes(data_path.read_bytes()+b'\n')
        result = self.cli('run', self.path)
        self.assertEqual(result.returncode, 2)
        self.assertIn('checksum differs', result.stdout)
        self.assertFalse(list(dse.resolve(self.path, self.config['output_dir']).glob('*/results.json')))
        data = json.loads(data_path.read_text())
        data['records'][0]['stages']['routed']['reported_signoff']['failing_endpoints']['Hold'] = 1
        write_json(data_path, data)
        data_path.with_suffix('.sha256').write_text(file_hash(data_path)+'\n')
        result = self.cli('preflight', self.path, '--json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('feasibility is inconsistent', result.stdout)

    def test_report_rejects_tampered_acquired_measurements(self):
        self.run_ok('run', self.path)
        out = dse.resolve(self.path, self.config['output_dir'])
        original_report = file_hash(out/'report.html')
        p = out/'random/results.json'
        state = json.loads(p.read_text())
        seed = state['observations'][state['seed_name']]
        seed['mapped']['metrics']['lut'] += 1
        write_json(p, state)
        result = self.cli('report', self.path)
        self.assertEqual(result.returncode, 2)
        self.assertIn('differs from the checksummed dataset', result.stderr)
        self.assertEqual(file_hash(out/'report.html'), original_report)

    def test_status_names_inference_design_and_timing_failure(self):
        self.config['policies'] = ['llm']
        write_json(self.path, self.config)
        store = PortableReplayStore(BUNDLE, llm_dse.catalog(self.config['study']), self.config['target'])
        seed = llm_dse.seed_name(store.rows)
        name = next(r['name'] for r in store.rows if r['name'] != seed)
        stages = store.seed(name)
        stages['routed'].update(feasible=False, reason='')
        stages['routed']['metrics']['setup_slack_ns'] = -.25
        out = dse.resolve(self.path, self.config['output_dir'])
        write_json(out/'experiment.json', dse.metadata(self.config))
        state = dict(policy='llm', status='running', seed_name=seed, selected=[name],
            observations={seed: store.seed(seed), name: stages}, attempts=dict(qualified=1, mapped=1, routed=1),
            history=[], proposals=[], active=None)
        write_json(out/'llm/results.json', state)
        write_json(out/'llm/llm/selection-2/call-1.json', {'started_at': 100})
        with patch('architecture_search.dse.time.time', return_value=130):
            item = dse.status(self.config, self.path)['policies'][0]
        self.assertEqual(item['active']['stage'], 'LLM inference')
        self.assertEqual(item['active']['elapsed_seconds'], 30)
        self.assertIn('setup timing failed', item['failures'][0]['reason'])
        state['active'] = dict(candidate_id=name, stage='routed', started_at=100)
        write_json(out/'llm/results.json', state)
        with patch('architecture_search.dse.time.time', return_value=130):
            item = dse.status(self.config, self.path)['policies'][0]
        self.assertEqual(item['active']['configuration'], stages['qualified']['row']['configuration'])

    def test_bad_credentials_in_json_and_live_preflight_are_actionable(self):
        bad = copy.deepcopy(self.config)
        bad['llm']['api_key'] = 'do-not-print-this'
        write_json(self.path, bad)
        result = self.cli('preflight', self.path)
        self.assertEqual(result.returncode, 2)
        self.assertIn('LLM_DSE_API_KEY', result.stderr)
        self.assertNotIn('do-not-print-this', result.stderr)
        live = dse.template(self.path, mode='live')
        with patch('architecture_search.dse.shutil.which', return_value=None), \
                patch('architecture_search.build_identity.verify', return_value={'verified': False}), \
                patch('architecture_search.dse.subprocess.run', side_effect=OSError('missing tool')), \
                patch('architecture_search.llm_evaluate.EvaluationStore') as native:
            result = dse.preflight(live, self.path)
        self.assertFalse(result['ok'])
        self.assertTrue(any('build_generators.sh' in c['detail'] for c in result['checks']))
        native.assert_not_called()

    def test_run_lock_does_not_block_read_only_status(self):
        out = dse.resolve(self.path, self.config['output_dir'])
        with dse.lock_output(out):
            result = self.cli('run', self.path)
            self.assertEqual(result.returncode, 2)
            self.assertIn('experiment is running', result.stderr)
            self.run_ok('status', self.path)


class EndpointCLITests(CLIBase):
    def server(self, code=200, redirect=False):
        class Handler(BaseHTTPRequestHandler):
            calls = []
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.calls.append(('GET', self.path))
                self.send_response(302 if redirect else code)
                if redirect:
                    self.send_header('Location', '/redirected')
                self.end_headers()
                self.wfile.write(json.dumps({'data': [{'id': 'test-model'}]}).encode())
            def do_POST(self):
                self.calls.append(('POST', self.path))
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                context = json.loads(body['messages'][1]['content'])
                assert all('metrics' not in c for c in context['candidates'])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(dict(choices=[dict(message=dict(content=json.dumps(
                    dict(candidate_id=context['eligible_ids'][0], rationale='selected from disclosed context'))))],
                    usage={'total_tokens': 10}, **{'fixture-secret': 'fixture-secret'})).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.config['policies'] = ['llm']
        self.config['llm'] = dict(base_url=f'http://127.0.0.1:{server.server_port}/v1', model='test-model')
        write_json(self.path, self.config)
        return Handler.calls

    def test_endpoint_preflight_run_and_keyless_completed_resume(self):
        calls = self.server()
        env = {'LLM_DSE_API_KEY': 'fixture-secret'}
        self.run_ok('preflight', self.path, env=env)
        self.run_ok('run', self.path, env=env)
        out = dse.resolve(self.path, self.config['output_dir'])
        self.assertEqual(sum(method=='POST' for method, _ in calls), 2)
        for p in out.rglob('*.json'):
            self.assertNotIn('fixture-secret', p.read_text())
        count = len(calls)
        self.run_ok('run', self.path)
        self.run_ok('report', self.path)
        self.assertEqual(len(calls), count)

    def test_auth_failure_and_redirect_never_start_trials(self):
        calls = self.server(code=401)
        result = self.cli('run', self.path, env={'LLM_DSE_API_KEY': 'fixture-secret'})
        self.assertEqual(result.returncode, 2)
        self.assertIn('HTTP 401', result.stdout)
        self.assertFalse(list(dse.resolve(self.path, self.config['output_dir']).glob('*/results.json')))
        self.assertFalse(any(method=='POST' for method, _ in calls))
        calls = self.server(redirect=True)
        result = self.cli('preflight', self.path, env={'LLM_DSE_API_KEY': 'fixture-secret'})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [('GET', '/v1/models')])


if __name__ == '__main__':
    unittest.main()
