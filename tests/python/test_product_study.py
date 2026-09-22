import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from architecture_search import product_cache,product_study,products
from architecture_search.model import artifact_manifest

class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.rtl=self.root/'rtl.sv';self.rtl.write_text('module Top;endmodule')
    def record(self,i,lut,interval):
        e=dict(implementation_passed=True,timing_clean=True,metrics=dict(lut=lut))
        e['integrity']=dict(version=1,inputs_unchanged=True,inputs=artifact_manifest([self.rtl]),
                           outputs=artifact_manifest([]),measurement=copy.deepcopy(e))
        return dict(id=str(i),correct=True,configuration=dict(generator='ngen',backend='streamed',lanes=2,pe=1),
                    evaluation=dict(metrics=dict(initiation_interval_cycles=interval)),evidence=dict(synthesis=e))
    def test_cache_rejects_changed_artifact_identity_and_measurement(self):
        key=dict(tool='2023.2',clock=8);e=self.record(0,10,20)['evidence']['synthesis']
        self.assertTrue(product_cache.put(self.root/'cache',key,e))
        self.assertEqual(product_cache.get(self.root/'cache',key),e)
        self.assertIsNone(product_cache.get(self.root/'cache',{**key,'clock':16}))
        damaged=copy.deepcopy(e);damaged['metrics']['lut']=0
        self.assertFalse(product_cache.put(self.root/'cache',dict(tool='other'),damaged))
        self.rtl.write_text('changed');self.assertIsNone(product_cache.get(self.root/'cache',key))
    def test_replay_hides_future_measurements_and_computes_frontier(self):
        records=[self.record(0,10,30),self.record(1,20,10),self.record(2,30,40)]
        seen=[]
        def choose(w,pending,observed,*args):
            self.assertTrue(all('evidence' not in r for r in pending))
            seen.append([r['id'] for r in observed]);return pending[0],None
        with patch.object(product_study.product_search,'choose',side_effect=choose):
            r=product_study.replay(dict(workload=products.workload(),candidates=records),budgets=[3],seeds=[0],policies=['enumerate'])
        self.assertEqual(seen,[[],['0'],['0','1']]);self.assertEqual(r['reference_frontier'],['0','1'])
        self.assertEqual(r['trials'][0]['trace'][-1]['hypervolume_fraction'],1)
        self.rtl.unlink()
        with self.assertRaises(ValueError):product_study.replay(dict(workload=products.workload(),candidates=records))
