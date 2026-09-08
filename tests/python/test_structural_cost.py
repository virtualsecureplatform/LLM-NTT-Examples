import unittest
from architecture_search.cost import predict


def config(pe,groups):
    return {'generator':'ngen','backend':'streamed','radix':2,'pe':pe,'stage_groups':groups,'reduction':'montgomery'}

class StructuralCost(unittest.TestCase):
    def test_replication_fit_predicts_held_out_configuration(self):
        samples=[{'configuration':config(p,g),'metrics':{'lut':100+20*g+30*p*g}} for p,g in ((1,1),(1,2),(4,1),(4,4))]
        result=predict(samples,config(2,3),'lut','structural')
        self.assertTrue(result['available'])
        self.assertAlmostEqual(result['estimate'],340)
        self.assertNotIn('passed',result)

    def test_underidentified_and_unrelated_families_are_not_guessed(self):
        samples=[{'configuration':config(1,g),'metrics':{'lut':100*g}} for g in (1,2,4)]
        self.assertFalse(predict(samples,config(4,2),'lut','structural')['available'])
        samples.append({'configuration':{**config(4,1),'reduction':'barrett'},'metrics':{'lut':900}})
        self.assertFalse(predict(samples,config(4,2),'lut','structural')['available'])
        self.assertFalse(predict(samples,config(1,1),'wns_ns','structural')['available'])
