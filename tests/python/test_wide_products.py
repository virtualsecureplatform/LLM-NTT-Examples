import unittest
import random
from architecture_search import wide_products as wide, wide_rtl


class WideProductContracts(unittest.TestCase):
    def test_full_throughput_fft_candidates_at_512(self):
        w = wide.workload(512,2147483647,'negacyclic',1<<32)
        rows = wide.candidates(w, dict(generators=['sgen'], sgen_backends=['full-throughput'],
                                      lanes=[2,4], fractional_bits=[30], guard_bits=[0,2]))
        self.assertEqual(len(rows),4)
        self.assertEqual({r['backend'] for r in rows},{'full-throughput'})
        self.assertEqual({r['integer_bits'] for r in rows},{41,43})
        self.assertEqual(wide.candidates({**w,'n':1024},dict(generators=['sgen'],
                         sgen_backends=['full-throughput'])),[])

    def test_rings_moduli_and_bounds(self):
        for ring in ('linear','cyclic','negacyclic'):
            w=wide.workload(8,127,ring);a=[0]*8;b=[0]*8;a[-1]=127;b[1]=-127
            out=wide.schoolbook(w,a,b)
            self.assertEqual(out[8 if ring=='linear' else 0],16129 if ring=='negacyclic' else -16129)
            self.assertEqual(wide.schoolbook({**w,'modulus':17},a,b),[v%17 for v in out])
            fields=wide.basis(w);q=1
            for f in fields:q*=f['q']
            self.assertGreater(q,2*wide.bound(w))

    def test_crt_recovers_signed_extrema_and_torus(self):
        rng=random.Random(1)
        for w in (wide.workload(256,32767),wide.tfhe_workload()):
            primes=[f['q'] for f in wide.basis(w)];bound=wide.bound(w)
            for x in [-bound,-1,0,1,bound]+[rng.randint(-bound,bound) for _ in range(20)]:
                self.assertEqual(wide.reconstruct([x%p for p in primes],primes),x)

    def test_radix16_signed_encoding(self):
        for lo,hi in ((-7,7),(-15,15),(-32767,32767),(0,(1<<32)-1)):
            w={**wide.workload(),'a_range':[lo,hi]};bits=wide.input_width(w,'a')
            for value in (lo,hi,0,lo//2,hi//2):
                actual=sum(wide.digit(value,i,bits,lo<0)<<(4*i) for i in range((bits+3)//4))
                self.assertEqual(actual,value)

    def test_omitted_low_digit_products_have_a_conservative_error_bound(self):
        rng=random.Random(7)
        for n in (8,16):
            w=wide.workload(n,2147483647,'negacyclic',1<<32)
            self.assertEqual(wide.omission_error_bound(w,1),n*225)
            self.assertEqual(wide.omission_error_bound(w,2),n*225*33)
            for count in (0,1,2):
                for _ in range(3):
                    a=[rng.randint(*w['a_range']) for _ in range(n)]
                    b=[rng.randint(*w['b_range']) for _ in range(n)]
                    exact=wide.schoolbook(w,a,b)
                    actual=wide.omitted_product(w,a,b,count)
                    errors=[(x-y+(1<<31))%(1<<32)-(1<<31) for x,y in zip(actual,exact)]
                    self.assertLessEqual(max(map(abs,errors)),wide.omission_error_bound(w,count))

    def test_low_diagonal_omission_changes_the_serial_fft_schedule(self):
        w=wide.workload(512,2147483647,'negacyclic',1<<32)
        leaf=wide.workload(512,15,'negacyclic')
        rtl0=wide_rtl.split_fft(w,leaf,0)
        rtl1=wide_rtl.split_fft(w,leaf,1)
        rtl2=wide_rtl.split_fft(w,leaf,2)
        self.assertIn('if(pair_index==35)',rtl0)
        self.assertIn('if(pair_index==34)',rtl1)
        self.assertIn('if(pair_index==32)',rtl2)

    def test_reject_unsupported_encodings(self):
        for patch in ({'a_range':[-1,1<<31]},{'modulus':1},{'n':4096},{'n':True},{'a_range':[True,7]}):
            with self.assertRaises(ValueError):wide.validate({**wide.workload(),**patch})


if __name__=='__main__':unittest.main()
