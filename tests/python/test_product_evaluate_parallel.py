import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from architecture_search import product_evaluate
from architecture_search.model import digest


class ParallelProductEvaluationTests(unittest.TestCase):
    def test_full_corpus_is_accounted_for_and_protocol_is_separate(self):
        corpus=[([i],[i+1]) for i in range(100)]
        seen={}

        def fake_evaluate(w,c,rtl,directory,timeout,simulator,**kwargs):
            seen[directory.name]=(kwargs['_corpus'],kwargs['_first_pass'],kwargs['_end_pass'])
            return dict(correct=True,inputs_unchanged=True,
                        metrics={'latency_cycles':12,'initiation_interval_cycles':4},
                        build={'returncode':0},test={'returncode':0},
                        verification={str(directory/'test.sv'):directory.name},
                        corpus_sha256=digest(kwargs['_corpus']))

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(product_evaluate.products,'vectors',return_value=corpus), \
                 patch.object(product_evaluate,'evaluate',side_effect=fake_evaluate):
                result=product_evaluate._parallel_large_fft(
                    {'n':1024,'version':2},{'generator':'sgen'},root/'SearchTop.sv',root,100,'verilator')
            self.assertTrue(result['correct'])
            self.assertEqual(result['corpus_sha256'],digest(corpus))
            self.assertEqual(result['metrics']['completed_products'],100)
            self.assertEqual(len(result['verification']),11)
            self.assertEqual([pair for i in range(10) for pair in seen[f'corpus-{i:02d}'][0]],corpus)
            self.assertTrue(all(seen[f'corpus-{i:02d}'][1:]==(0,1) for i in range(10)))
            self.assertEqual(seen['protocol'],(corpus[:8],1,4))


if __name__=='__main__':unittest.main()
