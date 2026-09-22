import unittest
import random
from architecture_search import wide_products as wide


class WideProductContracts(unittest.TestCase):
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

    def test_reject_unsupported_encodings(self):
        for patch in ({'a_range':[-1,1<<31]},{'modulus':1},{'n':4096},{'n':True},{'a_range':[True,7]}):
            with self.assertRaises(ValueError):wide.validate({**wide.workload(),**patch})


if __name__=='__main__':unittest.main()
