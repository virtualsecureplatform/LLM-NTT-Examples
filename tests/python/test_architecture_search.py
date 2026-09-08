import copy
import tempfile
from pathlib import Path
import unittest

from architecture_search import oracle
from architecture_search.model import frontier, run
from architecture_search.adapters import candidates


class OracleTests(unittest.TestCase):
    def test_fft_matches_definition_and_roundtrip(self):
        for n in (2,4,8,16,32):
            for negacyclic in (False,True):
                w={**oracle.field(n,16),'negacyclic':negacyclic,'direction':'forward'}
                oracle.validate(w)
                for v in oracle.vectors(w):
                    y=oracle.transform(v,w)
                    self.assertEqual(y,oracle.transform(v,w,direct=True))
                    inv={**w,'direction':'inverse'}
                    self.assertEqual(oracle.transform(y,inv),v)
                    self.assertEqual(oracle.transform(v,inv),oracle.transform(v,inv,direct=True))

    def test_negacyclic_convolution(self):
        w={**oracle.field(16,16),'negacyclic':True,'direction':'forward'}
        a,b=oracle.vectors(w)[-2:]
        fa,fb=oracle.transform(a,w),oracle.transform(b,w)
        q=int(w['q']); n=w['n']; expected=[0]*n
        for i,x in enumerate(a):
            for j,y in enumerate(b):
                expected[(i+j)%n]+=(1 if i+j<n else -1)*x*y
        actual=oracle.transform([x*y%q for x,y in zip(fa,fb)],{**w,'direction':'inverse'})
        self.assertEqual(actual,[v%q for v in expected])

    def test_rejects_bad_parameters(self):
        w=oracle.field(16,16)
        for change in ({'q':'561'},{'root':'1'},{'psi':'1','negacyclic':True},{'n':15},{'direction':'both'}):
            with self.assertRaises(ValueError):
                oracle.validate({**w,**change})
        with self.assertRaises(ValueError):
            oracle.field(65536,16)

    def test_large_fields_are_reproducible(self):
        for bits in (32,54,64):
            w=oracle.field(131072,bits)
            self.assertEqual(w,oracle.field(131072,bits))
            oracle.validate({**w,'negacyclic':True})


class EvidenceTests(unittest.TestCase):
    def record(self,name,latency,area,**changes):
        return {'id':name,'correct':True,'mode':'functional','evidence':{'route':{'passed':True,'target':{'part':'u280'},'metrics':{'latency':latency,'area':area}}},**changes}

    def test_tradeoffs_ties_and_dominance(self):
        records=[self.record('a',10,100),self.record('b',20,50),self.record('c',20,100),self.record('tie',10,100)]
        self.assertEqual(frontier(records,{'latency':'min','area':'min'},'route',{'part':'u280'}),['a','b','tie'])

    def test_evidence_gates(self):
        good=self.record('good',10,100)
        missing=self.record('missing',1,None)
        wrong=self.record('wrong',1,1);wrong['evidence']['route']['target']={'part':'other'}
        failed=self.record('failed',1,1,correct=False)
        lint=self.record('lint',1,1,mode='lint_only')
        nan=self.record('nan',float('nan'),0)
        self.assertEqual(frontier([good,missing,wrong,failed,lint,nan],{'latency':'min','area':'min'},'route',{'part':'u280'}),['good'])
        self.assertEqual(frontier([good],{'latency':'min'},'route',{'part':'u280'},{'area':99}),[])
        self.assertEqual(frontier([good],{'latency':'min'},'synthesis',{'part':'u280'}),[])

    def test_process_timeout_is_a_result(self):
        import sys
        with tempfile.TemporaryDirectory() as d:
            result=run([sys.executable,'-c','import time; time.sleep(10)'],Path(d),Path(d)/'log',0.05)
            self.assertEqual(result['returncode'],124)
            self.assertTrue(result['timed_out'])

    def test_illegal_space_is_not_silently_accepted(self):
        w={'kind':'generic',**oracle.field(16,16),'lanes':3}
        with self.assertRaises(ValueError):candidates(w,Path('.'))
        with self.assertRaises(ValueError):candidates({**w,'lanes':4},Path('.'),{'reductions':['unknown']})

if __name__=='__main__':unittest.main()

class SearchExtensionTests(unittest.TestCase):
    def test_sgen_composition_is_limited_to_real_switches(self):
        root=Path(__file__).resolve().parents[3]/'NGen'
        configs=candidates({'kind':'preset','task':'small_yata8x8_raintt_p27'},root,
                           {'backends':['microcoded'],'profiles':['baseline'],'transposes':['indexed','switch'],'permutations':['ngen','sgen']})
        self.assertEqual(len(configs),3)
        self.assertTrue(all(c['transpose']=='switch' for c in configs if c['generator']=='ngen-sgen'))

    def test_cost_predictions_are_not_evidence(self):
        from architecture_search.cost import predict,calibrate
        self.assertFalse(predict([],{'pe':1},'lut')['available'])
        model=calibrate([],{'n':16},{'part':'u280'})
        self.assertIsNone(model['leave_one_out']['lut']['mean_absolute_error'])
        samples=[{'configuration':{'pe':1},'metrics':{'lut':100}}, {'configuration':{'pe':2},'metrics':{'lut':200}}]
        self.assertLess(predict(samples,{'pe':1},'lut')['estimate'],predict(samples,{'pe':2},'lut')['estimate'])

    def test_partial_stage_groups_reject_radix_fusion(self):
        w={'kind':'generic',**oracle.field(16,16),'lanes':4}
        configs=candidates(w,Path('.'),{'pe':[1],'radix':[2,4],'stage_groups':[2]})
        self.assertTrue(all(c['radix']==2 and c['boundary']=='registered-ready-valid' for c in configs))
