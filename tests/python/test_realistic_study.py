import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import shutil
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('realistic_study', ROOT / 'scripts/run_realistic_study.py')
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
from architecture_search.model import artifact_manifest, file_hash, write_json


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rtl = self.root / 'design.v'
        self.rtl.write_text('module SearchTop; endmodule\n')
        self.campaign = {'workload': {'kind': 'generic', 'direction': 'forward', 'n': 4096, 'q': '2147565569'},
                         'target': {'clock_period_ns': 4}, 'resource_limits': study.CAPS,
                         'bandwidth': {'shared_bits_per_second': 64000000000, 'coefficient_bits': 64}}

    def record(self, pe=1, lut=100, throughput=1000):
        e = {'passed': True, 'implementation_passed': True, 'target': self.campaign['target'],
             'metrics': {'lut': lut, 'ff': 100, 'dsp': 4, 'bram': 1, 'uram': 0,
                         'wns_ns': 0.1, 'hold_slack_ns': 0.01,
                         'transforms_per_second': throughput, 'latency_ns': 1000}}
        e['integrity'] = {'version': 1, 'inputs_unchanged': True,
                          'inputs': artifact_manifest([self.rtl]), 'outputs': artifact_manifest([]),
                          'measurement': copy.deepcopy(e)}
        return {'id': str(pe), 'mode': 'functional', 'correct': True,
                'rtl_path': str(self.rtl), 'rtl_hash': file_hash(self.rtl),
                'configuration': {'pe': pe}, 'evidence': {'synthesis': e}}

    def test_missing_caps_metrics_and_wrong_target_fail_closed(self):
        self.assertTrue(study.eligible(self.record(), self.campaign))
        for key in study.CAPS:
            r = self.record()
            del r['evidence']['synthesis']['metrics'][key]
            self.assertFalse(study.eligible(r, self.campaign))
        for value in (None, float('nan'), -1, 50001):
            self.assertFalse(study.eligible(self.record(lut=value), self.campaign))
        c = copy.deepcopy(self.campaign)
        c['target']['clock_period_ns'] = 5
        self.assertFalse(study.eligible(self.record(), c))

    def test_mutated_rtl_or_measurement_and_unverified_evidence_rejected(self):
        r = self.record()
        r['evidence']['synthesis']['metrics']['lut'] += 1
        self.assertFalse(study.eligible(r, self.campaign))
        r = self.record()
        del r['evidence']['synthesis']['integrity']
        self.assertFalse(study.eligible(r, self.campaign))
        r = self.record()
        self.rtl.write_text('changed')
        self.assertFalse(study.eligible(r, self.campaign))

    def test_route_requires_setup_and_hold_even_with_pass_flag(self):
        r = self.record()
        r['evidence']['route'] = r['evidence']['synthesis']
        self.assertTrue(study.eligible(r, self.campaign, 'route'))
        e = r['evidence']['route']
        e['metrics']['hold_slack_ns'] = -0.01
        e['integrity']['measurement']['metrics']['hold_slack_ns'] = -0.01
        self.assertFalse(study.eligible(r, self.campaign, 'route'))

    def test_selection_is_stable_unique_and_bandwidth_capped(self):
        rows = [{'policy': method, 'record': self.record(pe, lut, speed)} for method, pe, lut, speed in
                [('random', 1, 100, 1000), ('llm', 2, 200, 200000), ('enumerate', 2, 200, 200000),
                 ('cost', 4, 400, 300000), ('cost', 8, 60000, 500000)]]
        selected = study.select_routes(rows, self.campaign)
        self.assertEqual([r['record']['id'] for r in selected], ['2', '1'])
        self.assertEqual(selected[0]['policy'], 'enumerate')
        self.assertEqual(selected, study.select_routes(list(reversed(rows)), self.campaign))
        self.assertEqual(study.select_routes(rows[:1], self.campaign)[0]['reasons'], ['fastest', 'lowest_lut'])
        self.campaign['workload']['direction'] = 'inverse'
        self.assertEqual(study.select_routes(rows, self.campaign), [])

    def test_trial_budget_and_binary_must_match(self):
        campaign_path = self.root / 'campaign.json'
        write_json(campaign_path, self.campaign)
        case = {'name': 'test', 'campaign': str(campaign_path)}
        binary = str(self.root / 'ngen.bat')
        p = {'seed': 2, 'evaluations_per_trial': 3, 'hours_per_trial': 2,
             'ngen_root': str(self.root), 'ngen_build': {'binary_sha256': 'abc'}, 'inputs': {binary: 'abc'}}
        manifest = {'campaign': self.campaign, 'policies': ['llm'], 'seeds': [2],
                    'evaluations_per_trial': 3, 'hours_total': 2, 'inputs': {binary: 'abc'}}
        path = self.root / 'trials/test/llm/manifest.json'
        write_json(path, manifest)
        self.assertEqual(study.trial_rows(self.root, case, 'llm', p), [])
        for key, value in [('hours_total', 12), ('evaluations_per_trial', 4), ('inputs', {binary: 'wrong'})]:
            write_json(path, {**manifest, key: value})
            with self.assertRaises(ValueError):
                study.trial_rows(self.root, case, 'llm', p)

    def test_orchestration_freezes_before_holdout_and_does_not_repeat(self):
        campaign_path = self.root / 'campaign.json'
        write_json(campaign_path, self.campaign)
        p = {'cases': [{'name': split, 'split': split, 'campaign': str(campaign_path)}
                       for split in ('development', 'held-out')],
             'policies': study.POLICIES, 'seed': 2, 'evaluations_per_trial': 3,
             'hours_per_trial': 2, 'ngen_root': str(self.root), 'route_selection': 'test',
             'verilator': {'path': '/unused/in/mocked/test'}}
        write_json(self.root / 'protocol.json', p)
        calls = []
        def fake_run(command, cwd, log, timeout):
            if 'held-out' in str(log):
                self.assertTrue((self.root / 'held-out-freeze.json').exists())
                self.assertTrue((self.root / 'development-summary.json').exists())
            self.assertEqual(timeout, 7260)
            self.assertEqual(command[command.index('--hours') + 1], '2')
            self.assertEqual(command[command.index('--evaluations') + 1], '3')
            calls.append(command)
            return {'returncode': 1}  # Failed attempts still consume their scheduled slot.
        def fake_summary(out, protocol):
            write_json(out / 'summary.json', {'attempts': len(calls)})
        with patch.dict(os.environ), patch.object(study, 'guard'), patch.object(study, 'run', side_effect=fake_run), \
                patch.object(study, 'trial_rows', return_value=[]), \
                patch.object(study, 'summarize', side_effect=fake_summary):
            study.execute(self.root, p)
            self.assertEqual(len(calls), 8)
            study.execute(self.root, p)
            self.assertEqual(len(calls), 8)
            state = study.read(self.root / 'state.json')
            state['active'] = {'key': 'interrupted'}
            write_json(self.root / 'state.json', state)
            with self.assertRaisesRegex(ValueError, 'Interrupted work'):
                study.execute(self.root, p)

    def test_summary_preserves_failed_runner_without_zero_performance(self):
        campaign_path = self.root / 'campaign.json'
        write_json(campaign_path, self.campaign)
        p = {'cases': [{'name': 'test', 'split': 'development', 'campaign': str(campaign_path)}],
             'policies': ['llm'], 'evaluations_per_trial': 3, 'limitations': ['No reference pool']}
        write_json(self.root / 'protocol.json', p)
        write_json(self.root / 'state.json', {'completed': {'trial/test/llm': {'process': {'returncode': 124}}}})
        result = study.summarize(self.root, p)
        self.assertEqual(result['terminal_trials'], 1)
        self.assertEqual(result['evaluations_completed'], 0)
        self.assertIsNone(result['trials'][0]['best_bandwidth_capped_transforms_per_second'])
        self.assertEqual(result['trials'][0]['stop_reason'], 'Runner ended without results.json')

    @unittest.skipUnless(shutil.which('verilator'), 'requires native Verilator')
    def test_long_rom_filename_runtime(self):
        directory = self.root / ('a' * 100) / ('b' * 100) / ('c' * 80)
        directory.mkdir(parents=True)
        memory = directory / 'control.mem'
        memory.write_text('2a\n')
        self.assertGreater(len(str(memory)), 256)
        rtl = self.root / 'test.sv'
        rtl.write_text('module test; reg [7:0] mem[0:0]; initial begin\n'
                       + '$readmemh("' + str(memory) + '", mem);\n'
                       + 'if (mem[0] !== 8\'h2a) $fatal(1, "bad ROM");\n'
                       + '$display("LONG_ROM_PASS"); $finish; end endmodule\n')
        environment = {**os.environ, 'NTT_STUDY_VERILATOR': shutil.which('verilator')}
        wrapper = ROOT / 'scripts/realistic-study-tools/verilator'
        build = subprocess.run(['bash', str(wrapper), '--binary', '--top-module', 'test', str(rtl)],
                               cwd=self.root, env=environment, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=120)
        self.assertEqual(build.returncode, 0, build.stdout)
        result = subprocess.run([str(self.root / 'obj_dir/Vtest')], cwd=self.root, env=environment,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('LONG_ROM_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
