"""External implementation gates must reject stale evidence before launching tools."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from architecture_search.model import file_hash
from architecture_search.oracle import field

ROOT=Path(__file__).resolve().parents[2]

class ExternalMeasurementGates(unittest.TestCase):
    def fixture(self,d):
        w={'kind':'generic',**field(16,16),'direction':'forward','negacyclic':True,'lanes':4}
        (d/'hardware').mkdir();(d/'stream').mkdir()
        package=d/'hardware/open_ntt_pkg.sv'
        package.write_text(f"localparam LOGN = 4;\nlocalparam LOGQ = {int(w['q']).bit_length()};\nlocalparam Q_VALUE = {w['q']};\nlocalparam PE = 1;\n")
        baseline={'generator':'OpenNTT','workload':w,'process':{'returncode':0},'configuration':{'pe':1},'artifacts':{'hardware/open_ntt_pkg.sv':file_hash(package)}}
        (d/'record.json').write_text(json.dumps(baseline))
        rtl=d/'stream/SearchTop.sv';rtl.write_text('module SearchTop; endmodule')
        test=d/'stream/test.sv';test.write_text('verified test fixture')
        stream={'correct':True,'boundary':{'kind':'registered-ready-valid','lanes':4},'rtl':str(rtl),'rtl_hash':file_hash(rtl),'verification':{str(test):file_hash(test)},'sources':[str(package)],'metrics':{}}
        (d/'stream/results.json').write_text(json.dumps(stream))
        campaign=d/'campaign.json';campaign.write_text(json.dumps({'workload':w}))
        return campaign,test,rtl

    def invoke(self,d,campaign):
        return subprocess.run(['python3',str(ROOT/'scripts/measure_external_ntt.py'),'--baseline-dir',str(d),'--campaign',str(campaign),'--output-dir',str(d/'measurement')],capture_output=True,text=True)

    def test_changed_oracle_artifact_is_rejected_before_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);campaign,test,rtl=self.fixture(d);test.write_text('changed')
            result=self.invoke(d,campaign)
            self.assertNotEqual(result.returncode,0);self.assertIn('verification artifact changed',result.stderr)
            self.assertFalse((d/'measurement').exists())

    def test_changed_wrapper_is_rejected_before_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);campaign,test,rtl=self.fixture(d);rtl.write_text('changed')
            result=self.invoke(d,campaign)
            self.assertNotEqual(result.returncode,0);self.assertIn('verified wrapper changed',result.stderr)
            self.assertFalse((d/'measurement').exists())

    def test_workload_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);campaign,test,rtl=self.fixture(d)
            c=json.loads(campaign.read_text());c['workload']['direction']='inverse';campaign.write_text(json.dumps(c))
            result=self.invoke(d,campaign)
            self.assertNotEqual(result.returncode,0);self.assertIn('workload mismatch',result.stderr)
