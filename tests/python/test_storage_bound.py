import unittest
from architecture_search.constraints import storage_bound

class StorageBound(unittest.TestCase):
    workload={'kind':'generic','n':65536,'q':str(2**53+1)}
    configuration={'generator':'ngen','backend':'streamed','boundary':'registered-ready-valid'}
    target={'part':'xcu280-fsvh2892-2L-e'}
    caps={'lut':10000,'ff':6000,'dsp':50,'bram':8,'uram':0}

    def bound(self,**changes):
        args={'workload':self.workload,'configuration':self.configuration,'target':self.target,'limits':self.caps};args.update(changes)
        return storage_bound(**args)

    def test_impossible_prefix_state_is_pruned(self):
        result=self.bound()
        self.assertTrue(result['pruned'])
        self.assertGreater(result['required_state_bits_lower_bound'],result['capacity_bits_upper_bound'])

    def test_missing_resource_is_not_zero(self):
        caps={k:v for k,v in self.caps.items() if k!='uram'}
        result=self.bound(limits=caps)
        self.assertFalse(result['available']);self.assertFalse(result['pruned'])

    def test_capacity_equality_and_dsp_state_are_optimistic(self):
        required=self.bound()['required_state_bits_lower_bound']
        caps={k:0 for k in self.caps};caps['ff']=required
        self.assertFalse(self.bound(limits=caps)['pruned'])
        caps['ff']-=1
        self.assertTrue(self.bound(limits=caps)['pruned'])
        caps['dsp']=1
        self.assertFalse(self.bound(limits=caps)['pruned'])

    def test_unknown_architecture_or_target_is_not_pruned(self):
        self.assertFalse(self.bound(target={'part':'unknown'})['available'])
        self.assertFalse(self.bound(configuration={**self.configuration,'generator':'llm'})['available'])
        with self.assertRaises(ValueError):self.bound(limits={**self.caps,'ff':float('nan')})
