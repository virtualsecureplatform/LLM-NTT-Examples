import json
from pathlib import Path
import tempfile
import unittest
from architecture_search.constraints import analyze,bandwidth_bound
from architecture_search.model import write_json
from architecture_search.search import report

W={'kind':'generic','n':256,'q':'2147484161','lanes':4}
T={'clock_period_ns':4.0}
C={'backend':'streamed','radix':2,'lanes':4,'pe':1,'stage_groups':1}

class Constraints(unittest.TestCase):
    def test_shared_link_accounts_for_both_vectors_and_padding(self):
        b=bandwidth_bound(W,{'shared_bits_per_second':16384000,'coefficient_bits':64})
        self.assertEqual(b['upper_transforms_per_second'],500)
        self.assertEqual(b['terms'][0]['bits_per_transform'],32768)
        with self.assertRaises(ValueError):bandwidth_bound(W,{'input_bits_per_second':1,'coefficient_bits':16})

    def test_issue_bound_prunes_only_when_optimistic_rate_is_insufficient(self):
        bound=analyze(W,C,T,requirements={'min_transforms_per_second':500000})
        self.assertEqual(bound['upper_transforms_per_second'],244140.625)
        self.assertTrue(bound['pruned'])
        self.assertFalse(analyze(W,{**C,'pe':4},T,requirements={'min_transforms_per_second':500000})['pruned'])
        # Equality is possible, not proven impossible.
        self.assertFalse(analyze(W,C,T,requirements={'min_transforms_per_second':244140.625})['pruned'])
        with self.assertRaises(ValueError):analyze(W,C,T,requirements={'min_transforms_per_second':float('nan')})

    def test_bandwidth_caps_frontier_without_overwriting_core_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);metrics={'latency_ns':100,'transforms_per_second':1000,'lut':10,'ff':10,'dsp':1,'bram':1,'uram':0}
            r={'id':'one','status':'complete','mode':'functional','correct':True,'configuration':C,'evidence':{'synthesis':{'passed':True,'target':T,'metrics':metrics}}}
            write_json(d/'candidates/one/record.json',r)
            campaign={'workload':W,'target':T,'bandwidth':{'shared_bits_per_second':8192000},'requirements':{'min_transforms_per_second':600}}
            result=report(d,campaign)
            self.assertEqual(result['frontiers']['synthesis'],[])
            m=result['candidates'][0]['evidence']['synthesis']['metrics']
            self.assertEqual(m['transforms_per_second'],1000)
            self.assertEqual(m['bandwidth_capped_transforms_per_second'],500)
            campaign['requirements']['min_transforms_per_second']=500
            self.assertEqual(report(d,campaign)['frontiers']['synthesis'],['one'])
            self.assertNotIn('bandwidth_capped_transforms_per_second',json.loads((d/'candidates/one/record.json').read_text())['evidence']['synthesis']['metrics'])
