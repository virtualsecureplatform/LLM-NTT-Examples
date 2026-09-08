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

    def test_incorrect_and_generation_failures_consume_budget(self):
        pool=[self.record('1',10,100),self.record('2',20,200)]
        observed=copy.deepcopy(pool)
        for record,status in zip(observed,('incorrect','generation_failed')):
            record.update(correct=False,status=status,evidence={})
            record.pop('rtl_hash')
        result=summary.score_trial(pool,observed,{}, {})
        self.assertEqual(result['evaluations'],2)
        self.assertEqual(result['failed_evaluations'],2)
        self.assertEqual(result['frontier_recall'],0)

    def test_wrong_target_is_not_a_scored_failure(self):
        pool=[self.record('1',10,100),self.record('2',20,200)]
        observed=copy.deepcopy(pool[:1])
        observed[0]['evidence']['synthesis']['target']={'part':'different'}
        with self.assertRaisesRegex(ValueError,'target differs'):
            summary.score_trial(pool,observed,{}, {})

    def test_cli_summarizes_completed_trial_with_generation_failure(self):
        import json
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reference=root/'reference';trials=root/'trials'
            def write(path,value):
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(value))
            pool=[self.record('1',10,100),self.record('2',20,200)]
            for record in pool:
                record['status']='complete'
                record['evidence']['synthesis']['implementation_passed']=True
            campaign={'workload':{'kind':'generic','n':128},'target':{}}
            write(reference/'manifest.json',{'campaign':campaign,'configurations':[r['configuration'] for r in pool],
                                            'identity':{'ngen_binary':'same-executable'}})
            write(reference/'report.json',{'workload':campaign['workload'],'candidates':pool})
            write(trials/'manifest.json',{'campaign':campaign,'policies':['enumerate'],'seeds':[2],
                                        'evaluations_per_trial':1,'inputs':{'/test/ngen.bat':'same-executable'}})
            write(trials/'results.json',{'trials':[{'policy':'enumerate','seed':2,'stop_reason':None,'evaluations_completed':1,
                                                  'elapsed_seconds':2,'trace':[{'candidate_id':'failed'}]}]})
            write(trials/'enumerate-2/candidates/failed/record.json',{'configuration':pool[0]['configuration'],'status':'generation_failed',
                                                                   'correct':False,'mode':'functional','evidence':{}})
            output=root/'summary.json'
            result=subprocess.run([sys.executable,str(Path(summary.__file__)),'--reference-dir',str(reference),
                                   '--trials-dir',str(trials),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            row=json.loads(output.read_text())['trials'][0]
            self.assertEqual(row['evaluations'],1)
            self.assertEqual(row['failed_evaluations'],1)
            self.assertEqual(row['frontier_recall'],0)
