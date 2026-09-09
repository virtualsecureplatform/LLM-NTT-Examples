import unittest
from architecture_search.policy import feedback
from architecture_search.model import digest

class Feedback(unittest.TestCase):
    def test_correct_timing_does_not_hide_resource_failure(self):
        row={'configuration':{'pe':4},'correct':True,'implementation_passed':True,'timing_passed':True,'metrics':{'lut':12000}}
        result=feedback([{'pe':1}],{'resource_limits':{'lut':10000},'observations':[row]})
        self.assertFalse(result['observations'][0]['resource_feasible'])
        self.assertEqual(result['observations'][0]['exceeded_limits']['lut']['measured'],12000)

    def test_failed_or_missing_measurements_are_unknown_not_zero(self):
        rows=[{'configuration':{'pe':1},'correct':True,'implementation_passed':False,'metrics':{'lut':0}},
              {'configuration':{'pe':2},'correct':True,'implementation_passed':True,'metrics':{}}]
        result=feedback([{'pe':4}],{'resource_limits':{'lut':100},'observations':rows})
        self.assertTrue(all(r['resource_feasible'] is None for r in result['observations']))
        self.assertEqual(result['candidate_advice'][digest({'pe':4})[:16]]['resource_estimates'],{})

    def test_advice_uses_only_matching_observed_family_and_keeps_all_candidates(self):
        low={'pe':1,'stage_groups':1,'backend':'streamed'};high={**low,'pe':4};other={**high,'backend':'other'}
        rows=[{'configuration':low,'correct':True,'implementation_passed':True,'metrics':{'lut':3000}}]
        result=feedback([high,other],{'resource_limits':{'lut':10000},'observations':rows})
        self.assertEqual(len(result['candidate_advice']),2)
        advice=result['candidate_advice'][digest(high)[:16]]['resource_estimates']['lut']
        self.assertEqual(advice['estimate'],12000);self.assertTrue(advice['estimated_over_limit'])
        self.assertEqual(result['candidate_advice'][digest(other)[:16]]['resource_estimates'],{})
