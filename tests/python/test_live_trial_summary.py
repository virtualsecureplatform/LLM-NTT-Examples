import copy
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('summary',Path(__file__).resolve().parents[2]/'scripts/summarize_live_policy_trials.py')
summary=importlib.util.module_from_spec(spec);spec.loader.exec_module(summary)

class TrialSummary(unittest.TestCase):
    def record(self,key,lut,rate):
        return {'id':key,'configuration':{'pe':int(key)},'rtl_hash':'rtl'+key,'correct':True,'mode':'functional',
                'evidence':{'synthesis':{'passed':True,'target':{},'metrics':{'latency_ns':100,'transforms_per_second':rate,
                  'lut':lut,'ff':10,'dsp':1,'bram':1,'uram':0}}}}

    def test_ids_are_matched_by_verified_configuration_and_rtl(self):
        pool=[self.record('1',10,100),self.record('2',20,200)]
        observed=copy.deepcopy(pool[:1]);observed[0]['id']='fresh-run-id'
        result=summary.score_trial(pool,observed,{}, {})
        self.assertEqual(result['frontier_recall'],0.5)
        self.assertEqual(result['recovered_reference_ids'],['1'])
        observed[0]['rtl_hash']='changed'
        with self.assertRaisesRegex(ValueError,'RTL differs'):summary.score_trial(pool,observed,{}, {})

    def test_failed_or_over_budget_measurements_do_not_recover_frontier(self):
        pool=[self.record('1',10,100),self.record('2',20,200)]
        observed=copy.deepcopy(pool);observed[0]['evidence']['synthesis']['passed']=False
        observed[1]['evidence']['synthesis']['metrics']['lut']=1000
        result=summary.score_trial(pool,observed,{}, {'lut':50})
        self.assertEqual(result['frontier_recall'],0)
        self.assertEqual(result['feasible_discoveries'],0)
        self.assertEqual(len(result['measurement_differences']),1)
