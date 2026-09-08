import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('snapshot',Path(__file__).resolve().parents[2]/'scripts/summarize_ntt_evidence.py')
snapshot=importlib.util.module_from_spec(spec);spec.loader.exec_module(snapshot)

class EvidenceSnapshot(unittest.TestCase):
    def test_changed_rtl_cannot_retain_cached_frontier_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            rtl=Path(tmp)/'top.sv';rtl.write_text('original')
            campaign={'workload':{'kind':'generic','n':16},'target':{}}
            record={'id':'a','configuration':{'generator':'ngen'},'correct':True,'mode':'functional','status':'complete',
                    'rtl_path':str(rtl),'rtl_hash':snapshot.file_hash(rtl),
                    'evidence':{'route':{'passed':True,'target':{},'metrics':{'lut':10,'ff':20,'dsp':1,'bram':2,'uram':0,
                                     'latency_ns':100,'transforms_per_second':1000}}}}
            report={'workload':campaign['workload'],'candidates':[record],'frontiers':{'route':['a']}}
            result=snapshot.summarize(report,campaign,'route')
            self.assertEqual(result['frontier'],['a'])
            self.assertEqual(result['rows'][0]['artifact_integrity'],'legacy-unverified')
            rtl.write_text('changed')
            result=snapshot.summarize(report,campaign,'route')
            self.assertEqual(result['frontier'],[])
            self.assertFalse(result['rows'][0]['qualified'])
            self.assertTrue(record['evidence']['route']['passed'])

    def test_missing_stage_is_not_a_zero_resource_measurement(self):
        report={'workload':{'kind':'generic'},'candidates':[{'id':'a','configuration':{},'correct':True,'mode':'functional','status':'complete','evidence':{}}]}
        result=snapshot.summarize(report,{'workload':report['workload'],'target':{}},'route')
        self.assertEqual(result['rows'][0]['metrics'],{})
        self.assertFalse(result['rows'][0]['qualified'])
