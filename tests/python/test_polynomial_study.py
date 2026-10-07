import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import polynomial_study as study
from architecture_search import wide_products as wide


class PolynomialStudyTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / 'studies/torus512.json').read_text())

    def test_grid_coverage_and_identity(self):
        rows = study.enumerate_points(self.spec)
        self.assertEqual(rows, study.enumerate_points(self.spec))
        self.assertEqual(len(rows), len({r['name'] for r in rows}))
        for name in study.workloads(self.spec):
            group = [r for r in rows if r['workload_name'] == name]
            requested = [r for r in group if 'requested_axes' in r]
            # One requested combination is represented by the arithmetic baseline.
            self.assertEqual(len(requested), 2 * 2 * 2 * 3 * 2 * 3 - 1)
            self.assertTrue(any(r['status'] == 'unsupported' for r in group))
            self.assertEqual(sum(r.get('dependency') is not None for r in group), 2)

    def test_operand_widths_and_crt(self):
        for name, w in study.workloads(self.spec).items():
            fields = wide.basis(w)
            import math
            self.assertGreater(math.prod(f['q'] for f in fields), 2 * wide.bound(w))
            self.assertEqual(wide.input_width(w, 'a'), 32)
            self.assertEqual(wide.input_width(w, 'b'), {'full-full': 32, 'full-byte': 8, 'full-ternary': 2}[name])
            for x in (-wide.bound(w), -1, 0, wide.bound(w)):
                self.assertEqual(wide.reconstruct([x % f['q'] for f in fields], [f['q'] for f in fields]), x)

    def test_fft_axes_and_rounding_parent_preserve_architecture(self):
        self.spec['workloads'] = self.spec['workloads'][:1]
        self.spec['sgen_axes'] = dict(sgen_backends=['compact','full-throughput'],lanes=[2,4],guard_bits=[0,2])
        self.spec['fractional_bits'] = [24,30]
        rows = study.enumerate_points(self.spec)
        self.assertEqual(len({r['name'] for r in rows}),len(rows))
        for r in rows:
            if r.get('configuration',{}).get('generator') == 'sgen':
                r['base_qualified'] = r['configuration']['fractional_bits'] == (24 if r['configuration']['backend']=='compact' else 30)
        dependencies = [r for r in rows if r.get('dependency')]
        self.assertEqual(len(dependencies),16)
        for r in dependencies:
            parent = study.fft_rounding_parent(rows,r)
            self.assertIsNotNone(parent)
            for k,v in r['fft_selector'].items():
                self.assertEqual(parent['configuration'][k],v)
            self.assertEqual(parent['configuration']['fractional_bits'],24 if r['fft_selector']['backend']=='compact' else 30)
        self.spec['sgen_axes']['bogus'] = [1]
        with self.assertRaises(ValueError): study.enumerate_points(self.spec)

    def test_approximation_and_commutativity(self):
        for w in study.workloads(self.spec).values():
            w = {**w, 'n': 8}
            vectors = study.corpus(w)
            for omitted in (0, 1, 2):
                c = dict(generator='sgen', omit_low_diagonals=omitted)
                metrics = study.error_metrics(w, c, 0, vectors)
                self.assertLessEqual(metrics['observed_max_abs_error'], metrics['max_abs_error'])
                swapped = {**w, 'a_range': w['b_range'], 'b_range': w['a_range']}
                for a, b in vectors[:6]:
                    self.assertEqual(study.expected(w, c, 0, a, b), study.expected(swapped, c, 0, b, a))
            for bits in (4, 8):
                m = study.error_metrics(w, study.BASE, bits, vectors)
                self.assertLessEqual(m['observed_max_abs_error'], 1 << (bits - 1))
        self.assertEqual(study.quantize(0xffffffff, 4), 0)
        self.assertEqual(study.centered_error(0, 0xffffffff), 1)
        self.assertEqual(wide.digit(-128, 1, 8, True), -8)
        self.assertEqual(wide.digit(-1, 0, 2, True), -1)

    def test_frontier_excludes_failures_and_keeps_ties(self):
        def row(name, error, cells):
            return {**dict.fromkeys(study.OBJECTIVES, 1), 'name': name, 'passed': True, 'max_abs_error': error, 'yosys_cells': cells}
        a = row('a', 0, 10); b = row('b', 8, 8); tie = row('tie', 0, 10)
        invalid = dict(row('bad', 0, 0), passed=False)
        self.assertEqual(set(study.frontier([a, b, tie, invalid], 0)), {'a', 'tie'})
        self.assertEqual(set(study.frontier([a, b, tie, invalid], 8)), {'a', 'b', 'tie'})

    def test_resume_artifact_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); path = out / 'test.sv'; path.write_text('original')
            row = dict(passed=True, configuration={'fractional_bits': 30},
                       artifacts={'test.sv': study.file_hash(path)})
            self.assertTrue(study.reusable(row, out))
            self.assertFalse(study.reusable(row, out, {'configuration': {'fractional_bits': 32}}))
            self.assertTrue(study.reusable(row, out, row))
            path.write_text('changed')
            self.assertFalse(study.reusable(row, out))
            path.unlink()
            self.assertFalse(study.reusable(row, out))

    def test_certificate_rejection_does_not_simulate(self):
        w = next(iter(study.workloads(self.spec).values()))
        c = wide.candidates(w, {'generators': ['sgen'], 'fractional_bits': [24]})[0]
        row = study.point('full-full', w, c, 'arithmetic')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); rtl = out / 'base.sv'; rtl.write_text('')
            rtl.with_suffix('.json').write_text(json.dumps({'certificate': {'qualified': False}}))
            with patch.object(study.wide_backend, 'generate', return_value=({'returncode': 0}, rtl)), \
                 patch.object(study.wide_backend, 'qualification_valid', return_value=False), \
                 patch.object(study.product_evaluate, 'evaluate') as evaluate:
                study.screen(row, out, 1, 'iverilog')
                self.assertEqual(row['status'], 'certificate-rejected')
                evaluate.assert_not_called()

    def test_successful_asymmetric_checks_use_separate_timing_and_protocol(self):
        w = {**study.workloads(self.spec)['full-byte'], 'n': 16}
        row = study.point('full-byte', w, study.BASE.copy(), 'arithmetic')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); rtl = out / 'base.sv'; rtl.write_text('module SearchTop(); endmodule')
            rtl.with_suffix('.json').write_text(json.dumps({'certificate': {'qualified': True}}))
            checks = []
            def evaluate(w, c, rtl, directory, timeout, simulator, **kw):
                checks.append((w, directory.name, len(kw['_corpus']), kw['_first_pass'], kw['_end_pass']))
                return {'correct': True, 'metrics': {'latency_cycles': 20, 'initiation_interval_cycles': 10}}
            with patch.object(study.wide_backend, 'generate', return_value=({'returncode': 0}, rtl)), \
                 patch.object(study.wide_backend, 'qualification_valid', return_value=True), \
                 patch.object(study.product_evaluate, 'evaluate', side_effect=evaluate), \
                 patch.object(study, 'collected_counts', return_value={'passed': True, 'counts': {
                     'cells': 100, 'memory_bits': 200, 'register_bits': 30, 'multipliers': 2}}):
                study.screen(row, out, 1, 'iverilog')
            self.assertTrue(row['passed'])
            self.assertEqual([(c[1], c[2]) for c in checks],
                             [('correctness', 101), ('timing', 12), ('protocol', 64), ('swapped', 101)])
            self.assertEqual(checks[-1][0]['a_range'], [-128, 127])
            self.assertEqual(checks[2][3:], (0, 4))
            self.assertEqual(row['initiation_interval_cycles'], 10)
            self.assertTrue(study.reusable(row, out))

    def test_report_frontiers_are_workload_separated(self):
        rows = []
        for name, w in study.workloads(self.spec).items():
            r = study.point(name, w, study.BASE.copy(), 'arithmetic')
            r.update(dict.fromkeys(study.OBJECTIVES, 10))
            r.update(max_abs_error=0, passed=True, status='screened')
            rows.append(r)
        rounded = copy.deepcopy(rows[0]); rounded.update(name='rounded', quant_bits=4, max_abs_error=8)
        rounded['yosys_cells'] += 2; rows.append(rounded)
        with tempfile.TemporaryDirectory() as d:
            study.save(Path(d), self.spec, rows)
            report = json.loads((Path(d) / 'results.json').read_text())
            for name in study.workloads(self.spec):
                self.assertEqual(len(report['frontiers'][name]['0']), 1)
            self.assertEqual(rows[-1]['delta_from_exact']['yosys_cells'], 2)
            self.assertIn('fractional_bits', (Path(d) / 'all-points.csv').read_text())

    def test_correctness_timeout_skips_timing_protocol_swap_and_synthesis(self):
        w = {**study.workloads(self.spec)['full-byte'], 'n': 16}
        row = study.point('full-byte', w, study.BASE.copy(), 'arithmetic')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); rtl = out / 'base.sv'; rtl.write_text('module SearchTop; endmodule')
            rtl.with_suffix('.json').write_text(json.dumps({'certificate': {'qualified': True}}))
            with patch.object(study.wide_backend, 'generate', return_value=({'returncode': 0}, rtl)) as gen, \
                 patch.object(study.wide_backend, 'qualification_valid', return_value=True), \
                 patch.object(study.product_evaluate, 'evaluate', return_value={'correct': False, 'test': {'timed_out': True}}) as ev, \
                 patch.object(study, 'collected_counts') as synth:
                study.screen(row, out, 1, 'iverilog')
            self.assertEqual(ev.call_count, 1)
            self.assertEqual(gen.call_count, 1)
            synth.assert_not_called()
            self.assertEqual(row['reason'], 'correctness')
            self.assertEqual(row['status'], 'timeout')
            self.assertEqual(set(row['simulation']), {'correctness'})

    def test_shared_fft_correctness_failure_does_not_run_timing_or_protocol(self):
        w = study.workloads(self.spec)['full-full']
        c = wide.candidates(w, {'generators': ['sgen'], 'fractional_bits': [30]})[0]
        row = study.point('full-full', w, c, 'arithmetic')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); rtl = root / 'base.sv'; rtl.write_text('module SearchTop; endmodule')
            rtl.with_suffix('.json').write_text(json.dumps({'certificate': {'qualified': True}}))
            with patch.object(study.wide_backend, 'generate', return_value=({'returncode': 0}, rtl)), \
                 patch.object(study.wide_backend, 'qualification_valid', return_value=True), \
                 patch.object(study, 'error_metrics', return_value={'max_abs_error': 0}), \
                 patch.object(study.product_simulation, 'compile_simulator', return_value=({'build': {'returncode': 0}}, {'max_frames': 12})) as compile_sim, \
                 patch.object(study.product_simulation, 'evaluate_shards', return_value={'correct': False, 'test': {'timed_out': True}}) as shards, \
                 patch.object(study.product_evaluate, 'evaluate') as evaluate, \
                 patch.object(study, 'collected_counts') as synth:
                study.screen(row, root, 1, 'verilator')
            compile_sim.assert_called_once()
            shards.assert_called_once()
            evaluate.assert_not_called()
            synth.assert_not_called()
            self.assertEqual(row['reason'], 'correctness')
            self.assertEqual(set(row['simulation']), {'correctness'})

    def test_cross_campaign_reuse_preserves_provenance_and_rejects_arithmetic_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); rtl = root / 'rtl.sv'; rtl.write_text('original')
            old = dict(schema='test', spec={}, selected=['pass'], tools={}, generators={}, corpora={},
                       image_sha256=None, sources={'architecture_search/wide_products.py': 'same',
                                                  'architecture_search/product_evaluate.py': 'old'})
            new = {**old, 'selected': None, 'sources': {**old['sources'], 'architecture_search/product_evaluate.py': 'new',
                                    'architecture_search/product_simulation.py': 'added'}}
            study.write_json(root / 'manifest.json', old)
            study.write_json(root / 'results.json', {'points': [dict(name='pass', passed=True,
                artifacts={'rtl.sv': study.file_hash(rtl)}), dict(name='fail', passed=False)]})
            imported, identity = study.import_results(root / 'results.json', new)
            self.assertEqual(set(imported), {'pass'})
            self.assertEqual(imported['pass']['reused_from'], identity)
            self.assertTrue(study.reusable(imported['pass'], root / 'new-root'))
            new['sources']['architecture_search/wide_products.py'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'arithmetic'):
                study.import_results(root / 'results.json', new)

    def test_architecture_grid_override(self):
        spec = copy.deepcopy(self.spec)
        spec['ngen_axes'] = {k: [v[0]] for k, v in study.AXES.items()}
        rows = study.enumerate_points(spec)
        self.assertFalse(any(r['phase'] == 'architecture' for r in rows))
        spec['ngen_axes']['radix'] = [3]
        with self.assertRaises(ValueError): study.enumerate_points(spec)

    def test_invalid_spec(self):
        spec = copy.deepcopy(self.spec); spec['quant_bits'] = [4]
        with self.assertRaises(ValueError): study.enumerate_points(spec)


if __name__ == '__main__':
    unittest.main()
