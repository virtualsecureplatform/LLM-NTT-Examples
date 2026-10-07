import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collections import Counter
from architecture_search import product_evaluate, product_simulation, wide_products as wide
from architecture_search.model import digest, file_hash


class ShardedProductSimulationTests(unittest.TestCase):
    def test_protocol_preserves_bubble_and_stalled_inputs(self):
        corpus = [([i], [i + 1]) for i in range(101)]
        tasks = product_simulation.protocol_tasks(corpus, 4)
        all_frames = [pair for _, frames, _, _, _ in tasks for pair in frames]
        self.assertEqual(Counter(map(digest, all_frames)), Counter(map(digest, corpus[:64])))
        resets = [task for task in tasks if task[2:4] == (0, 4)]
        self.assertEqual([task[1][0] for task in resets], corpus[:8])
        self.assertTrue(all('+stall_frames=1' in task[4] and '+steady_frames=1' in task[4] for task in resets))
        self.assertEqual(len(all_frames), 64)

    def test_all_101_frames_checked_once_and_failed_shards_not_counted(self):
        corpus = [([i], [i + 1]) for i in range(101)]
        seen = {}
        def evaluate(w, c, rtl, target, timeout, simulator, **kw):
            frames = kw['_corpus']; seen[target.name] = frames
            good = target.name != 'corpus-025'
            return dict(correct=good, inputs_unchanged=True, verification={},
                        build={'returncode': 0}, test={'returncode': 0 if good else 124, 'timed_out': not good})
        with tempfile.TemporaryDirectory() as d, patch.object(product_evaluate, 'evaluate', side_effect=evaluate), patch('builtins.print'):
            result = product_simulation.evaluate_shards({}, {}, Path(d) / 'rtl.sv', Path(d),
                10, corpus, None, {'max_frames': 12}, workers=4, shard_size=4)
        self.assertEqual([frame for name in sorted(seen) for frame in seen[name]], corpus)
        self.assertFalse(result['correct'])
        self.assertEqual(result['requested_frames'], 101)
        self.assertEqual(result['checked_frames'], 100)
        self.assertTrue(result['test']['timed_out'])
        self.assertEqual(result['corpus_sha256'], digest(corpus))

    def test_partial_shard_reuse_checks_inputs_and_artifacts(self):
        frames = [([1], [2])]; compiled = {'max_frames': 12}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.sv'; p.write_text('original')
            result = dict(correct=True, compiled_signature=digest(compiled), corpus_sha256=digest(frames),
                          pass_range=[0, 1], runtime_args=[], verification={str(p): file_hash(p)})
            self.assertTrue(product_simulation.reusable_shard(result, frames, 0, 1, (), compiled))
            self.assertFalse(product_simulation.reusable_shard(result, [([2], [3])], 0, 1, (), compiled))
            self.assertFalse(product_simulation.reusable_shard(result, frames, 0, 4, (), compiled))
            p.write_text('mutation')
            self.assertFalse(product_simulation.reusable_shard(result, frames, 0, 1, (), compiled))

    def test_512_fft_compile_uses_O3(self):
        w = wide.workload(512, 7, modulus=1 << 32)
        commands = []
        def run(cmd, cwd, log, timeout):
            commands.append(cmd); log.write_text('PASS polynomial product\n')
            return {'returncode': 0, 'command': cmd}
        with tempfile.TemporaryDirectory() as d, patch.object(product_evaluate, 'run', side_effect=run):
            root = Path(d); rtl = root / 'rtl.sv'; rtl.write_text('module SearchTop; endmodule')
            product_evaluate.evaluate(w, {'generator': 'sgen', 'arithmetic': 'direct'}, rtl,
                root / 'compile', 1, 'verilator', _corpus=[([0] * 512, [0] * 512)], _compile_only=True)
        self.assertEqual(len(commands), 1)
        self.assertIn('-O3', commands[0][commands[0].index('-CFLAGS') + 1])

    def test_compiled_identity_and_capacity_guard(self):
        w = wide.workload(8, 7, modulus=1 << 32); c = {'generator': 'ngen'}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); rtl = root / 'rtl.sv'; rtl.write_text('module SearchTop; endmodule')
            bench = root / 'bench.sv'; bench.write_text(product_evaluate.testbench(w, 1, 100000))
            executable = root / 'sim'; executable.write_text('test executable')
            compiled = dict(workload_sha256=digest(w), configuration_sha256=digest(c), rtl_sha256=file_hash(rtl),
                max_frames=1, testbench=str(bench), testbench_sha256=file_hash(bench),
                executable=str(executable), executable_sha256=file_hash(executable))
            frames = [([0] * 8, [0] * 8)]
            with self.assertRaisesRegex(ValueError, 'capacity'):
                product_evaluate.evaluate(w, c, rtl, root / 'too-large', 1, 'verilator',
                    _corpus=frames * 2, _compiled=compiled)
            executable.write_text('mutated executable')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                product_evaluate.evaluate(w, c, rtl, root / 'mutated', 1, 'verilator',
                    _corpus=frames, _compiled=compiled)


if __name__ == '__main__': unittest.main()
