import copy
import unittest
from architecture_search.replay import trial,validate_pool

TARGET={'clock_period_ns':4.0}

def record(i,lut,throughput,passed=True):
    return {'id':str(i),'status':'complete' if passed else 'hardware_failed','correct':True,'mode':'functional','rtl_hash':str(i),
            'configuration':{'generator':'ngen','pe':i+1,'radix':2,'lanes':4},
            'evidence':{'synthesis':{'implementation_passed':True,'passed':passed,'target':TARGET,
            'metrics':{'lut':lut,'ff':lut,'dsp':10,'bram':4,'uram':0,'latency_ns':1000,'transforms_per_second':throughput}}}}

class Replay(unittest.TestCase):
    def test_failed_timing_consumes_budget_but_never_recovers_frontier(self):
        pool=[record(0,1,999,False),record(1,50,100),record(2,100,200)]
        validate_pool({'candidates':pool},TARGET,'synthesis')
        result=trial(pool,TARGET,'synthesis',2,'enumerate',1)
        self.assertEqual(result['trace'][0]['feasible_discoveries'],0)
        self.assertEqual(result['final']['frontier_recall'],0.5)
        self.assertEqual(len(result['trace']),2)

    def test_unobserved_metrics_do_not_change_first_choice(self):
        pool=[record(0,10,100),record(1,20,200),record(2,30,300)]
        changed=copy.deepcopy(pool)
        a=trial(pool,TARGET,'synthesis',2,'cost',9)
        for r in changed:
            if r['id']!=a['trace'][0]['candidate_id']:r['evidence']['synthesis']['metrics']['lut']*=100
        b=trial(changed,TARGET,'synthesis',2,'cost',9)
        self.assertEqual(a['trace'][0]['candidate_id'],b['trace'][0]['candidate_id'])
        self.assertEqual(a['trace'][1]['candidate_id'],b['trace'][1]['candidate_id'])
        self.assertEqual(a['trace'][1]['lut_prediction_before_measurement'],b['trace'][1]['lut_prediction_before_measurement'])
        self.assertIsNone(a['trace'][0]['lut_prediction_before_measurement'])
        self.assertEqual(a['trace'][1]['lut_prediction_before_measurement']['samples'],1)

    def test_minimum_sustainable_rate_is_applied_to_policy_scores(self):
        pool=[record(0,10,100),record(1,20,200)]
        for r in pool:r['evidence']['synthesis']['metrics']['bandwidth_capped_transforms_per_second']=min(r['evidence']['synthesis']['metrics']['transforms_per_second'],150)
        result=trial(pool,TARGET,'synthesis',2,'enumerate',1,objectives={'lut':'min','bandwidth_capped_transforms_per_second':'max'},minimums={'bandwidth_capped_transforms_per_second':125})
        self.assertEqual(result['trace'][0]['feasible_discoveries'],0)
        self.assertEqual(result['final']['feasible_discoveries'],1)
        self.assertEqual(result['final']['frontier_recall'],1)

    def test_full_budget_recovers_reference_frontier(self):
        pool=[record(0,10,100),record(1,20,200),record(2,30,150)]
        for policy in ('enumerate','random','cost','llm'):
            result=trial(pool,TARGET,'synthesis',3,policy,2,llm_order=[r['configuration'] for r in reversed(pool)])
            self.assertEqual(result['final']['frontier_recall'],1)
            self.assertEqual(len({s['candidate_id'] for s in result['trace']}),3)

    def test_pool_rejects_revision_mixing_and_missing_measurements(self):
        pool=[record(0,10,100),record(1,20,200)]
        validate_pool({'candidates':pool},TARGET,'synthesis')
        pool[1]['configuration']=pool[0]['configuration']
        with self.assertRaisesRegex(ValueError,'duplicate configuration'):validate_pool({'candidates':pool},TARGET,'synthesis')
        pool=[record(0,10,100),record(1,20,200)];del pool[1]['evidence']['synthesis']['metrics']['lut']
        with self.assertRaisesRegex(ValueError,'missing hardware objective'):validate_pool({'candidates':pool},TARGET,'synthesis')

    def test_sequential_selector_receives_only_acquired_metrics(self):
        pool=[record(0,10,100),record(1,20,200),record(2,30,300)]
        calls=[]
        def select(remaining,observed,step):
            self.assertEqual(len(observed),step)
            self.assertTrue(all('metrics' not in c and 'id' not in c for c in remaining))
            calls.append(copy.deepcopy((remaining,observed)))
            selected=copy.deepcopy(remaining[0])
            remaining[0]['pe']=999 # caller mutation cannot alter the reference
            return selected
        result=trial(pool,TARGET,'synthesis',3,'llm',2,llm_selector=select)
        self.assertEqual(result['final']['frontier_recall'],1)
        self.assertEqual(calls[0][1],[])
        self.assertEqual(calls[1][1][0]['metrics']['lut'],10)
        self.assertEqual(pool[0]['configuration']['pe'],1)
        with self.assertRaisesRegex(ValueError,'unknown or already'):
            trial(pool,TARGET,'synthesis',1,'llm',2,llm_selector=lambda *args:{'pe':999})
