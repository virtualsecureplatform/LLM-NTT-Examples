import unittest
from architecture_search.acquisition import choose

class Acquisition(unittest.TestCase):
    def test_unobserved_outcomes_cannot_influence_choice(self):
        legal=[{'pe':1},{'pe':2},{'pe':4}]
        first,prediction=choose(legal,[],'cost',3,0)
        self.assertIn(first,legal);self.assertIsNone(prediction)
        remaining=[c for c in legal if c!=first]
        measured=[{'configuration':first,'metrics':{'lut':100}}]
        selected,prediction=choose(remaining,measured,'cost',3,1)
        self.assertIn(selected,remaining);self.assertEqual(prediction['samples'],1)
        self.assertEqual(prediction['estimate'],100)

    def test_child_search_rejects_out_of_space_configuration(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        from architecture_search.search import main
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            selected=Path(tmp)/'configuration.json';selected.write_text(json.dumps({'pe':999}))
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
                main(['--campaign',str(root/'campaigns/smoke.json'),'--configuration-json',str(selected),'--output-dir',str(Path(tmp)/'output'),'--mode','plan'])
            self.assertEqual(error.exception.code,2)
            self.assertFalse((Path(tmp)/'output').exists())

    def test_failed_measurement_is_not_a_zero_resource_sample(self):
        legal=[{'pe':1},{'pe':2}]
        observed=[{'configuration':{'pe':4},'metrics':{}}]
        selected,prediction=choose(legal,observed,'cost',1,1)
        self.assertIn(selected,legal);self.assertIsNone(prediction)
        self.assertEqual(choose(legal,[],'enumerate',1,0)[0],{'pe':1})
        with self.assertRaises(ValueError):choose([],[],'random',1,0)
