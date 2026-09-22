import unittest
from architecture_search import autontt_research as study,oracle
class AutoNTTResearchTests(unittest.TestCase):
    def trace(self,arch):
        a=list(range(8));f=oracle.transform(a,dict(n=8,q='17',root='9'))
        if arch=='I':f=[f[int(f'{i:03b}'[::-1],2)] for i in range(8)]
        return '\n'.join(['LLMNTT field 8 17 9 0','LLMNTT input '+' '.join(map(str,a)),
                         'LLMNTT forward '+' '.join(map(str,f)),'LLMNTT inverse '+' '.join(map(str,a))])
    def test_independent_direction_order_and_field_checks(self):
        for arch in ('I','D','H'):
            text=self.trace(arch);self.assertTrue(study.verify_trace(text,arch)['passed'])
            with self.assertRaises(ValueError):study.verify_trace(text.replace('inverse 0','inverse 1'),arch)
            with self.assertRaises(ValueError):study.verify_trace(text.replace('8 17 9','8 17 1'),arch)
    def test_unrecognized_hosts_and_approximate_comparisons_rejected(self):
        with self.assertRaises(ValueError):study.instrument_host('int main(){}')
        with self.assertRaises(ValueError):study.compare(dict(correct=True,boundary='off-chip'),{})
        with self.assertRaises(ValueError):study.matched_campaign(study.verify_trace(self.trace('I'),'I'),'forward')
