import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class PresetReportMerge(unittest.TestCase):
    def check(self,change=None):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);rtl=d/'top.v';rtl.write_text('module top;endmodule\n')
            campaign={'workload':{'kind':'preset','task':'fixture'},'target':{'part':'fixture','clock_period_ns':4}}
            record={'id':'failed','configuration':{'generator':'fixture'},'status':'incorrect','mode':'functional','correct':False,'rtl_path':str(rtl),'rtl_hash':hashlib.sha256(rtl.read_bytes()).hexdigest(),'evidence':{'simulation':{'passed':False,'target':campaign['target'],'metrics':{}}}}
            data={'workload':campaign['workload'],'candidates':[record]}
            if change=='target':record['evidence']['simulation']['target']={'part':'different'}
            if change=='rtl':rtl.write_text('changed\n')
            (d/'campaign.json').write_text(json.dumps(campaign));(d/'report.json').write_text(json.dumps(data))
            process=subprocess.run([sys.executable,str(ROOT/'scripts/compare_preset_runs.py'),'--campaign',str(d/'campaign.json'),'--reports',str(d/'report.json'),'--output-dir',str(d/'out')],capture_output=True,text=True)
            if change:
                self.assertNotEqual(process.returncode,0)
                self.assertIn('target mismatch' if change=='target' else 'RTL changed',process.stderr)
            else:
                self.assertEqual(process.returncode,0,process.stderr)
                result=json.loads((d/'out/report.json').read_text())
                self.assertEqual(result['counts'],{'incorrect':1})
                self.assertEqual(result['frontiers']['simulation'],[])
                self.assertTrue(json.loads((d/'out/manifest.json').read_text())['artifact_hashes_at_import'])

    def test_retains_failed_evidence(self):self.check()
    def test_rejects_target_mismatch(self):self.check('target')
    def test_rejects_changed_rtl(self):self.check('rtl')
