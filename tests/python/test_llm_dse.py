import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from architecture_search import device, llm_dse
from architecture_search.llm_evaluate import EvaluationStore, require_target, strict_route
from architecture_search.model import artifact_manifest, file_hash, write_json

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    return (llm_dse.catalog(json.loads((ROOT/'studies/torus512-llm-demo.json').read_text())),
            device.load_target(ROOT/'studies/u280-kernel-harness.json'))


class FakeStore:
    identity = {'fixture': 1}

    def __init__(self, rows, fail_qualification=False):
        self.rows = {r['name']: r for r in rows}
        self.calls, self.cache, self.fail = [], {}, fail_qualification
        self.stop = None

    def result(self, name, stage, owner='seed'):
        row = dict(copy.deepcopy(self.rows[name]), passed=True, max_abs_error=0,
                   latency_cycles=2000, initiation_interval_cycles=1000, yosys_cells=200,
                   memory_bits=1000, register_bits=2000, multipliers=10)
        resources = dict(lut=100+int(name[-2:], 16), ff=200, dsp=10, bram36=10, uram=0)
        return dict(stage=stage, passed=not(stage=='qualified' and self.fail), row=row,
                    metrics=resources, feasible=stage=='routed', cache_hit=False,
                    physical_seconds=1, hardware_seconds=1, owner=owner)

    def seed(self, name):
        values = {s: self.result(name, s) for s in ('qualified', 'mapped', 'routed')}
        for value in values.values():
            value['passed'] = True
        return values

    def validate_observations(self, observations):
        pass

    def evaluate(self, name, stage, observations, owner):
        self.calls.append((name, stage))
        value = self.result(name, stage, owner)
        self.cache[name, stage] = value
        if stage == self.stop:
            self.stop = None
            raise KeyboardInterrupt()
        return value

    def recover(self, name, stage, observations, owner):
        return self.cache[name, stage]


class AcquisitionTests(unittest.TestCase):
    def test_catalog_identity_and_visibility(self):
        rows, target = inputs()
        self.assertEqual(len(rows), 24)
        name = llm_dse.seed_name(rows)
        self.assertEqual(name, 'full-ternary-2be26723e0be400f')
        self.assertEqual(len({r['name'] for r in rows}), 24)
        store = FakeStore(rows)
        state = dict(seed_name=name, selected=[], observations={name: store.seed(name)},
                     attempts={'routed': 0})
        context = llm_dse.public_context(rows, state, target, 4, 2)
        self.assertEqual(len(context['eligible_ids']), 23)
        self.assertNotIn(name, context['eligible_ids'])
        self.assertEqual([o['candidate_id'] for o in context['observations']], [name])
        self.assertFalse(any('metrics' in r or 'row' in r for r in context['candidates']))
        self.assertNotIn('physical_seconds', json.dumps(context))

    def test_feedback_budgets_and_resume_do_not_repeat_stages(self):
        rows, target = inputs()
        class Client:
            def __init__(self):
                self.contexts = []
            def select(self, context, directory):
                self.contexts.append(copy.deepcopy(context))
                return dict(candidate_id=context['eligible_ids'][0], rationale='feedback test')
        with tempfile.TemporaryDirectory() as directory:
            store, client = FakeStore(rows), Client()
            store.stop = 'mapped'
            with self.assertRaises(KeyboardInterrupt):
                llm_dse.run_search(rows, target, store, directory, client=client)
            interrupted = json.loads((Path(directory)/'results.json').read_text())
            self.assertEqual(interrupted['attempts']['mapped'], 1)
            self.assertEqual(interrupted['active']['stage'], 'mapped')
            state = llm_dse.run_search(rows, target, store, directory, client=client, resume=True)
            self.assertEqual(state['attempts'], dict(qualified=4, mapped=4, routed=2))
            self.assertEqual(len(store.calls), 10)
            self.assertEqual(len(set(store.calls)), 10)
            self.assertEqual(len(state['observations']), 5)
            self.assertEqual(sum('routed' in o['stages'] for o in client.contexts[2]['observations']), 2)
            again = llm_dse.run_search(rows, target, store, directory, client=client, resume=True)
            self.assertEqual(state, again)
            self.assertEqual(len(store.calls), 10)
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                llm_dse.run_search(rows, target, store, directory, max_candidates=6, resume=True)

    def test_failed_qualification_consumes_candidates_without_mapping(self):
        rows, target = inputs()
        with tempfile.TemporaryDirectory() as directory:
            store = FakeStore(rows, fail_qualification=True)
            state = llm_dse.run_search(rows, target, store, directory, policy='random')
            self.assertEqual(state['attempts'], dict(qualified=4, mapped=0, routed=0))
            self.assertEqual(state['progress']['feasible'], 1)
            self.assertEqual(len(state['selected']), 4)

    def test_hypervolume_fixed_reference_and_equal_points(self):
        points = [dict(name='a', lut=10, modeled_products_per_second=10),
                  dict(name='b', lut=20, modeled_products_per_second=20),
                  dict(name='c', lut=30, modeled_products_per_second=15),
                  dict(name='equal', lut=10, modeled_products_per_second=10)]
        self.assertEqual(set(llm_dse.frontier(points)), {'a', 'b', 'equal'})
        self.assertEqual(llm_dse.hypervolume(points, 100, 10), 1.7)
        self.assertEqual(llm_dse.hypervolume([], 100, 10), 0)

    def test_promotion_uses_alternating_objectives_and_not_mapped_slack(self):
        rows, target = inputs()
        store = FakeStore(rows)
        names = [r['name'] for r in rows[:3]]
        observations = {n: store.seed(n) for n in names}
        for n in names:
            del observations[n]['routed']
            observations[n]['mapped']['metrics']['setup_slack_ns'] = -1
        observations[names[1]]['qualified']['row']['initiation_interval_cycles'] = 500
        observations[names[2]]['mapped']['metrics']['lut'] = 1
        state = dict(selected=names+[rows[3]['name']], observations=observations, attempts={'routed': 0})
        self.assertEqual(llm_dse.promote(state, target, 2), names[1])
        state['attempts']['routed'] = 1
        observations[names[1]]['routed'] = {'passed': False}
        self.assertEqual(llm_dse.promote(state, target, 2), names[2])
        state['attempts']['routed'] = 2
        self.assertIsNone(llm_dse.promote(state, target, 2))


class EndpointTests(unittest.TestCase):
    def server(self, replies):
        class Handler(BaseHTTPRequestHandler):
            calls = []
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.calls.append((self.path, body, self.headers.get('Authorization')))
                reply = replies[min(len(self.calls)-1, len(replies)-1)]
                status = reply if isinstance(reply, int) else 200
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                result = {'error': 'server echo test-key'} if status != 200 else dict(
                    choices=[dict(message=dict(content=reply))], usage={'total_tokens': 10}, echo='test-key')
                self.wfile.write(json.dumps(result).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}/v1', Handler.calls

    def test_json_contract_corrections_redaction_and_saved_selection(self):
        url, calls = self.server(['not json', json.dumps({'candidate_id': 'used', 'rationale': 'bad'}),
                                 json.dumps({'candidate_id': 'next', 'rationale': 'test-key'})])
        with patch.dict(os.environ, LLM_DSE_API_KEY='test-key'), tempfile.TemporaryDirectory() as directory:
            client = llm_dse.LLMClient(url, 'test-model')
            with patch('architecture_search.llm_dse.time.sleep'):
                result = client.select({'eligible_ids': ['next']}, directory)
                self.assertEqual(result['candidate_id'], 'next')
                self.assertEqual(result['rationale'], '[REDACTED]')
                self.assertEqual(client.select({'eligible_ids': ['next']}, directory), result)
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[0][0], '/v1/chat/completions')
            self.assertEqual(calls[0][2], 'Bearer test-key')
            self.assertEqual(calls[0][1]['response_format'], {'type': 'json_object'})
            for path in Path(directory).glob('*.json'):
                self.assertNotIn('test-key', path.read_text())
                self.assertNotIn('Authorization', path.read_text())

    def test_auth_stops_immediately_and_never_persists_error_body(self):
        url, calls = self.server([401])
        with patch.dict(os.environ, LLM_DSE_API_KEY='test-key'), tempfile.TemporaryDirectory() as directory:
            client = llm_dse.LLMClient(url)
            for _ in range(2):
                with self.assertRaises(llm_dse.LLMAuthenticationError):
                    client.select({'eligible_ids': ['next']}, directory)
            self.assertEqual(len(calls), 1)
            self.assertNotIn('test-key', (Path(directory)/'call-1.json').read_text())

    def test_retry_budget_survives_resume_and_missing_key_fails(self):
        url, calls = self.server([503])
        with patch.dict(os.environ, LLM_DSE_API_KEY='test-key'), tempfile.TemporaryDirectory() as directory:
            client = llm_dse.LLMClient(url)
            with patch('architecture_search.llm_dse.time.sleep'):
                for _ in range(2):
                    with self.assertRaisesRegex(llm_dse.LLMError, 'three-request'):
                        client.select({'eligible_ids': ['next']}, directory)
            self.assertEqual(len(calls), 3)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(llm_dse.LLMError, 'LLM_DSE_API_KEY'):
                llm_dse.LLMClient(url)


class EvidenceTests(unittest.TestCase):
    def test_unsealed_recovery_is_terminal_and_live_orphans_block_recovery(self):
        rows, _ = inputs()
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationStore.__new__(EvaluationStore)
            store.rows = {r['name']: r for r in rows}
            store.root = Path(directory)
            store.identity = {'context': {'build': 1}}
            store._import = lambda name, stage: None
            name = rows[0]['name']
            with patch('architecture_search.llm_evaluate.live_process', return_value=True):
                with self.assertRaisesRegex(ValueError, 'live worker'):
                    store.recover(name, 'mapped', {}, 'owner')
            self.assertFalse((store.root/name/'mapped'/'result.json').exists())
            with patch('architecture_search.llm_evaluate.live_process', return_value=False):
                result = store.recover(name, 'mapped', {}, 'owner')
                again = store.recover(name, 'mapped', {}, 'owner')
            self.assertFalse(result['passed'])
            self.assertEqual(result['reason'], 'interrupted-unsealed')
            self.assertEqual(result, again)

    def test_failed_routes_consume_budget_without_entering_frontier(self):
        rows, target = inputs()
        class FailedRoutes(FakeStore):
            def evaluate(self, name, stage, observations, owner):
                result = super().evaluate(name, stage, observations, owner)
                if stage == 'routed':
                    result.update(passed=True, feasible=False, reason='setup timing failed')
                return result
        with tempfile.TemporaryDirectory() as directory:
            state = llm_dse.run_search(rows, target, FailedRoutes(rows), directory, policy='analytical')
            self.assertEqual(state['attempts']['routed'], 2)
            self.assertEqual(state['progress']['feasible'], 1)
            self.assertEqual(state['progress']['frontier'], [state['seed_name']])

    def test_cache_owner_costs_identity_and_artifact_changes(self):
        rows, _ = inputs()
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationStore.__new__(EvaluationStore)
            store.rows = {r['name']: r for r in rows}
            store.root = Path(directory)
            store.identity = {'context': {'build': 1}}
            name = rows[0]['name']
            folder = store.root/name/'mapped'
            folder.mkdir(parents=True)
            artifact = folder/'design.dcp'
            artifact.write_text('checkpoint')
            value = dict(passed=True, hardware_seconds=3, physical_seconds=3)
            store._seal(name, 'mapped', 'first', value)
            self.assertEqual(store._load(name, 'mapped', 'first')['physical_seconds'], 3)
            self.assertEqual(store._load(name, 'mapped', 'second')['physical_seconds'], 0)
            self.assertTrue(store._load(name, 'mapped', 'second')['cache_hit'])
            artifact.write_text('changed checkpoint')
            with self.assertRaisesRegex(ValueError, 'cache identity or artifacts changed'):
                store._load(name, 'mapped', 'second')

    def test_context_and_raw_endpoint_signoff(self):
        _, target = inputs()
        with self.assertRaises(ValueError):
            require_target(dict(target, implementation_context='registered-harness-v1'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cp = root/'design.dcp'
            cp.write_text('cp')
            evidence = {'checkpoint': str(cp)}
            report = root/'timing.rpt'
            report.write_text('Setup : 0 Failing Endpoints\nHold : 1 Failing Endpoints, Worst Slack -0.000ns\nPW : 0 Failing Endpoints\n')
            with patch('architecture_search.llm_evaluate.device.feasible', return_value=True):
                self.assertFalse(strict_route({}, evidence, None, target))
                report.write_text('Setup : 0 Failing Endpoints\nHold : 0 Failing Endpoints\nPW : 0 Failing Endpoints\n')
                proof = dict(passed=True, checkpoint_sha256=file_hash(cp))
                proof['integrity'] = dict(version=1, inputs_unchanged=True,
                    inputs=artifact_manifest([cp]), outputs=artifact_manifest([]),
                    measurement=dict(proof))
                write_json(root/'clock.json', proof)
                self.assertTrue(strict_route({}, evidence, root/'clock.json', target))
                cp.write_text('changed')
                self.assertFalse(strict_route({}, evidence, root/'clock.json', target))


if __name__ == '__main__':
    unittest.main()
