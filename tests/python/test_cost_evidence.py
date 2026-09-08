import copy
import unittest
from architecture_search.cost import calibrate

class CostEvidence(unittest.TestCase):
    def record(self):
        return {'mode':'functional','status':'complete','correct':True,'rtl_hash':'rtl-a',
                'configuration':{'backend':'streamed','radix':2,'pe':1,'stage_groups':1},
                'evidence':{'synthesis':{'target':{},'implementation_passed':True,
                                        'passed':False,'metrics':{'lut':42,'wns_ns':-1}}}}

    def test_failed_timing_remains_a_cost_observation_but_not_invalid_evidence(self):
        original=self.record()
        records=[original]
        for mutation in ('lint','running','missing_hash','integrity','target'):
            r=copy.deepcopy(original);r['rtl_hash']=mutation
            if mutation=='lint':r['mode']='lint'
            if mutation=='running':r['status']='running'
            if mutation=='missing_hash':r.pop('rtl_hash')
            if mutation=='integrity':r['evidence']['synthesis']['integrity']={'version':1,'inputs_unchanged':False}
            if mutation=='target':r['evidence']['synthesis']['target']={'part':'other'}
            records.append(r)
        records.append(copy.deepcopy(original))
        result=calibrate([{'workload':{},'candidates':records}],{}, {})
        self.assertEqual(len(result['samples']),1)
        self.assertEqual(result['samples'][0]['metrics']['wns_ns'],-1)
        self.assertEqual(result['evidence_integrity'],{'verified':0,'legacy-unverified':1})
        self.assertEqual(sum(result['rejected_records'].values()),6)
        self.assertEqual(result['rejected_records']['invalid_integrity'],1)
