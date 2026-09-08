import unittest
from architecture_search.proteus import memory_index, drain_cycles


class ProteusMemoryLayout(unittest.TestCase):
    def test_sdf_spectral_layout(self):
        self.assertEqual([memory_index(i,16,'sdf',True) for i in range(16)],
                         [0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15])

    def test_mdc_bank_layout(self):
        self.assertEqual([memory_index(i,16,'mdc',True) for i in range(16)],
                         [0,4,2,6,1,5,3,7,8,12,10,14,9,13,11,15])
        for n in (16,256,4096):
            for architecture in ('sdf','mdc'):
                for spectral in (False,True):
                    self.assertEqual(sorted(memory_index(i,n,architecture,spectral) for i in range(n)),list(range(n)))

    def test_drain_covers_observed_completion_pipeline(self):
        record={'workload':{'n':256},'parameters':{'DELAY_ADD':1,'DELAY_MUL':2,'DELAY_RED':6,'DELAY_DIV2':1}}
        self.assertGreater(drain_cycles(record),354)
        record['parameters']['DELAY_RED']=12
        self.assertGreater(drain_cycles(record),354+8*6)
