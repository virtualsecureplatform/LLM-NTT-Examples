import copy
import unittest
from architecture_search import oracle
from architecture_search.benchmark_suite import campaign,definitions,fixed_field,polynomial_product_check

class RealisticBenchmarks(unittest.TestCase):
    def trace(self):
        # Independent fixture with four distinct valid primes; no hardware outcomes.
        domains=[]
        for bits in (40,60):
            d=oracle.field(8192,bits);domains.append(d);q=int(d['q'])+16384
            while not oracle.is_prime(q):q+=16384
            domains.append(fixed_field(8192,q))
        return {'correct':True,'seal_revision':'119dc32e135cb89c1062076a69310d4413ebc824','samples':[{'correct':True,'workload':{**d,'negacyclic':True,'direction':direction}} for d in domains for direction in ('forward','inverse')]}
    def test_domains_and_holdout_separation(self):
        cases=definitions(self.trace());self.assertEqual(len(cases),11)
        self.assertEqual({c['name'] for c in cases if c['split']=='held-out'},{'fhe16k54','fhe64k54'})
        for case in cases:
            for direction in ('forward','inverse'):
                c=campaign(case,direction);oracle.validate(c['workload']);self.assertNotIn('metrics',c)
        m=next(c for c in cases if c['name']=='mldsa256');self.assertEqual(m['domain']['psi'],'1753')
        self.assertFalse(next(c for c in cases if c['name']=='goldilocks1024')['negacyclic'])
    def test_reject_incomplete_ntt_and_unverified_trace(self):
        with self.assertRaises(ValueError):fixed_field(256,3329)
        with self.assertRaises(ValueError):definitions({'correct':False})
        t=self.trace();t['samples'][0]['workload']['root']='1'
        with self.assertRaises(ValueError):definitions(t)
    def test_sparse_product_independent_of_transform_oracle(self):
        d=oracle.field(16,12)
        for negacyclic in (True,False):self.assertTrue(polynomial_product_check(d,negacyclic))
    def test_targets_not_shared_mutable_and_singleton_validation(self):
        case=definitions(self.trace())[0];a=campaign(case,'forward',True);b=campaign(case,'inverse',True)
        a['target']['io_delays_ns']['input_min']=123
        self.assertEqual(b['target']['io_delays_ns']['input_min'],.5)
        self.assertEqual(b['space']['pe'],[2]);self.assertEqual(b['stages'],['simulation'])
