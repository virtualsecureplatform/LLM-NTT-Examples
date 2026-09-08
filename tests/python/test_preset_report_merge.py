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

    def test_external_report_root_preserves_artifact_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); origin=d/'original';origin.mkdir()
            rtl=origin/'top.v';rtl.write_text('module top;endmodule\n')
            artifact=origin/'timing.rpt';artifact.write_text('timing fixture\n')
            campaign={'workload':{'kind':'preset','task':'fixture'},'target':{'part':'fixture','clock_period_ns':4}}
            record={'id':'failed','configuration':{'generator':'fixture'},'status':'incorrect','mode':'functional','correct':False,'rtl_path':str(rtl),'rtl_hash':hashlib.sha256(rtl.read_bytes()).hexdigest(),'evidence':{'simulation':{'passed':False,'target':campaign['target'],'metrics':{},'reports':{'timing':'timing.rpt'}}}}
            source=d/'report.json';source.write_text(json.dumps({'workload':campaign['workload'],'candidates':[record]}))
            config=d/'campaign.json';config.write_text(json.dumps(campaign))
            command=[sys.executable,str(ROOT/'scripts/compare_preset_runs.py'),'--campaign',str(config),'--reports',str(source),'--report-root',str(source),str(origin),'--output-dir']
            result=subprocess.run(command+[str(d/'out')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            manifest=json.loads((d/'out/manifest.json').read_text())
            self.assertEqual(manifest['report_roots'][str(source)],str(origin))
            self.assertEqual(manifest['artifact_hashes_at_import'][str(artifact)],hashlib.sha256(artifact.read_bytes()).hexdigest())
            merged=json.loads((d/'out/report.json').read_text())
            self.assertEqual(merged['candidates'][0]['evidence']['simulation']['reports']['timing'],str(artifact))
            artifact.unlink()
            result=subprocess.run(command+[str(d/'missing')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('missing hardware report artifact',result.stderr)
