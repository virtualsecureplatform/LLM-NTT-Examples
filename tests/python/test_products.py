import copy
import json
from pathlib import Path
import tempfile
import unittest
from fractions import Fraction

from architecture_search import products, numerics, constraints, release
from architecture_search.fft_model import transform
from architecture_search.model import digest


def descriptor(n=32, integer=24, frac=24, family='CTDFT'):
    width=integer+frac; twfrac=width-2
    entries=[]
    for exponent in range(n):
        bounds=numerics.trig_interval(n,exponent)
        values=[int((lo+hi)/2*(1<<twfrac))&((1<<width)-1) for lo,hi in bounds]
        entries.append(dict(exponent=exponent,real_bits=str(values[0]),imag_bits=str(values[1])))
    return dict(schema='sgen-search-v1',numeric_model='sgen-radix2-v1',family=family,
                transform_size=n,streaming_width=2,radix=2,scaling='1',ram_control='Dual',
                complex_packing='imag-high-real-low',multiply_rounding='signed-floor-after-each-real-product',
                addition='fixed-width-wrap',integer_bits=integer,fractional_bits=frac,
                twiddle_integer_bits=2,twiddle_fractional_bits=twfrac,twiddles=entries,rtl_sha256='test')


class ProductContracts(unittest.TestCase):
    def test_schoolbook_wrap_sign_and_integer_field_range(self):
        for n in (8,16,32,64,256):
            w=products.workload(n);products.validate(w);f=products.field(w)
            self.assertGreater(f['q'],2*n*49)
            a=[0]*n;b=[0]*n;a[-1]=7;b[1]=-7
            self.assertEqual(products.schoolbook(a,b),[49]+[0]*(n-1))
            self.assertEqual(pow(f['psi'],n,f['q']),f['q']-1)

    def test_product_does_not_accept_approximate_or_wide_contracts(self):
        for change in ({'n':1024},{'n':True},{'ring':'cyclic'},{'correctness':'empirical'},{'coefficient_bound':8},{'extra':1}):
            with self.assertRaises(ValueError):products.validate({**products.workload(),**change})

    def test_candidate_legality_and_aliases(self):
        w=products.workload(16); cs=products.candidates(w)
        self.assertEqual(len(cs),len({digest(c) for c in cs}))
        self.assertEqual({c['backend'] for c in cs},{'streamed','stage-parallel','fully-parallel','full-throughput','compact'})
        for c in cs:
            if c['generator']=='ngen':
                self.assertEqual(4%(c['radix'].bit_length()-1),0)
                if c['stage_groups']>1:self.assertEqual(c['radix'],2)
                if c['backend']=='fully-parallel':self.assertEqual(c['lanes'],16)
        for space in ({'radix':[3]},{'generators':['fft']},{'typo':1},{'configurations':[{}]}):
            with self.assertRaises(ValueError):products.candidates(w,space)

    def test_product_traffic_counts_two_operands_and_one_result(self):
        w=products.workload();b=constraints.product_bandwidth(w,{'shared_bits_per_second':30400})
        self.assertEqual(b['terms'][0]['bits_per_product'],16*(8+11))
        self.assertEqual(b['upper_products_per_second'],100)
        self.assertTrue(constraints.analyze(w,{}, {'clock_period_ns':4}, {'shared_bits_per_second':30400}, {'min_products_per_second':101})['pruned'])


class NumericalCertificates(unittest.TestCase):
    def test_pi_and_trig_enclosures(self):
        lo,hi=numerics.pi_interval()
        self.assertLess(Fraction('3.14159265358979323846264338327950288419716939937510'),lo)
        self.assertLess(hi,Fraction('3.14159265358979323846264338327950288419716939937511'))
        for i,expected in [(0,(1,0)),(8,(0,-1)),(16,(-1,0)),(24,(0,1))]:
            self.assertEqual(numerics.trig_interval(32,i),tuple((Fraction(v),Fraction(v)) for v in expected))

    def test_conservative_certificate_rejects_precision_overflow_and_tampering(self):
        w=products.workload();a=descriptor();b={**a,'family':'ICTDFT'}
        cert=numerics.certify(w,a,b)
        self.assertTrue(cert['qualified'])
        bad=descriptor(frac=4)
        self.assertFalse(numerics.certify(w,bad,{**bad,'family':'ICTDFT'})['qualified'])
        small=descriptor(integer=3)
        self.assertFalse(numerics.certify(w,small,{**small,'family':'ICTDFT'})['qualified'])
        changed=copy.deepcopy(a);changed['twiddles'][1]['real_bits']='0'
        self.assertFalse(numerics.certify(w,changed,b)['qualified'])
        changed=copy.deepcopy(a);changed['twiddles'].pop()
        with self.assertRaises(ValueError):numerics.certify(w,changed,b)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'core.sv';path.write_text('altered')
            self.assertFalse(numerics.certificate_valid(cert,w,[a,b],[path,path]))

    def test_fixed_point_factorizations_and_inverse_gain(self):
        for forward,inverse in [('CTDFT','ICTDFT'),('ItPeaseFused','IItPeaseFused')]:
            a=descriptor(n=16,family=forward);b={**a,'family':inverse};f=a['fractional_bits']
            # Impulses at zero and constant signed inputs are exactly representable.
            self.assertEqual(transform([(1<<f,0)]+[(0,0)]*15,a),[(1<<f,0)]*16)
            expected=[(-16<<f,0)]+[(0,0)]*15
            self.assertEqual(transform([(-1<<f,0)]*16,a),expected)
            self.assertEqual(transform([(1<<f,0)]*16,b),[(16<<f,0)]+[(0,0)]*15)


class ReleaseAcceptance(unittest.TestCase):
    def test_covering_matrix_is_legal_and_exercises_every_backend(self):
        for n in (8,16,32,64,256):
            campaign=release.campaign(n,matrix=True)
            cs=products.candidates(campaign['workload'],campaign['space'])
            self.assertEqual(cs,campaign['space']['configurations'])
            self.assertEqual({c['backend'] for c in cs},
                             {'streamed','stage-parallel','fully-parallel','full-throughput','compact'})
            self.assertEqual(campaign['budget']['functional'],len(cs))

    def test_missing_failed_or_unqualified_backend_prevents_completion(self):
        campaign=release.campaign()
        rows=[dict(id=str(i),configuration=c,status='complete',correct=True,
                   declared={'certificate':{'qualified':True}})
              for i,c in enumerate(campaign['space']['configurations'])]
        self.assertTrue(release.accept({'candidates':rows},campaign)['passed'])
        self.assertFalse(release.accept({'candidates':rows[:-1]},campaign)['passed'])
        bad=copy.deepcopy(rows);bad[0]['status']='incorrect'
        self.assertFalse(release.accept({'candidates':bad},campaign)['passed'])
        bad=copy.deepcopy(rows);bad[-1]['declared']['certificate']['qualified']=False
        self.assertFalse(release.accept({'candidates':bad},campaign)['passed'])
        self.assertFalse(release.accept({'candidates':rows+rows[:1]},campaign)['passed'])
        self.assertFalse(release.accept({'candidates':rows},release.campaign(hardware=True))['passed'])

    def test_sgen_only_dispatch_does_not_check_ngen_build(self):
        from architecture_search import search
        from unittest.mock import patch
        import contextlib, io
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);campaign=release.campaign()
            campaign['space']={'generators':['sgen'],'sgen_backends':['compact'],
                               'lanes':[2],'fractional_bits':[24]}
            path=root/'campaign.json';path.write_text(json.dumps(campaign))
            seen=[]
            def verify(root,binary=None,generator='ngen'):
                seen.append(generator)
                return {'verified':False,'error':'intentional missing build'}
            with patch.object(search,'verify',side_effect=verify),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    search.main(['--campaign',str(path),'--output-dir',str(root/'output'),
                                 '--ngen-root',str(root/'absent-ngen'),'--mode','run'])
            self.assertEqual(seen,['sgen'])


if __name__=='__main__':unittest.main()
