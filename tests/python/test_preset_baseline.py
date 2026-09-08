import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

class PresetBaseline(unittest.TestCase):
    def test_lint_or_changed_inputs_cannot_become_functional_evidence(self):
        for mode,mutate in [('lint_only',False),('verilator_test',True)]:
            with self.subTest(mode=mode,mutate=mutate),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);rtl=root/'reference.sv';rtl.write_text('module reference;endmodule')
                campaign=root/'campaign.json';campaign.write_text(json.dumps({'workload':{'kind':'preset','task':'small_yata8x8_raintt_p27'}}))
                out=root/'output'
                def fake_run(command,cwd,log,timeout):
                    directory=Path(command[command.index('--build-dir')+1]);directory.mkdir(parents=True)
                    (directory/'results.json').write_text(json.dumps({'correct':True,'mode':mode,'metrics':{}}))
                    if mutate:rtl.write_text('module changed;endmodule')
                    return {'returncode':0}
                args=['evaluate_preset_baseline.py','--campaign',str(campaign),'--rtl',str(rtl),'--output-dir',str(out)]
                with patch.object(sys,'argv',args),patch('architecture_search.model.run',side_effect=fake_run),patch('architecture_search.model.source_identity',return_value={'revision':'test'}),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as error:
                    runpy.run_path(str(ROOT/'scripts/evaluate_preset_baseline.py'),run_name='__main__')
                self.assertEqual(error.exception.code,1)
                result=json.loads((out/'report.json').read_text())
                self.assertFalse(result['candidates'][0]['correct'])
                self.assertEqual(result['frontiers']['simulation'],[])
