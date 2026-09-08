import unittest
from architecture_search.openntt import physical_address,reordered
from architecture_search.oracle import field,transform,vectors

class MemoryLayout(unittest.TestCase):
    def test_documented_two_pe_layout(self):
        self.assertEqual([physical_address(i,16,2,'nr_input') for i in range(16)],
                         [0,1,2,3,8,9,10,11,4,5,6,7,12,13,14,15])
        self.assertEqual([physical_address(i,16,2,'nr_output') for i in range(16)],
                         [0,4,1,5,2,6,3,7,8,12,9,13,10,14,11,15])

    def test_layout_is_bijective(self):
        for n in (64,256,16384):
            for pe in (1,2,4,8):
                for layout in ('nr_input','nr_output'):
                    self.assertEqual(sorted(physical_address(i,n,pe,layout) for i in range(n)),list(range(n)))

    def test_forward_inverse_corpora_use_reversed_spectral_order(self):
        w={'kind':'generic',**field(64,16),'negacyclic':True,'direction':'forward'}
        for direction in ('forward','inverse'):
            w['direction']=direction
            a,b=reordered(w,2)
            for frame,vector in enumerate(vectors(w)):
                expected=transform(vector,w)
                for i in range(64):
                    r=int(f'{i:06b}'[::-1],2)
                    if direction=='forward':
                        self.assertEqual(a[frame][physical_address(i,64,2,'nr_input')],vector[i])
                        self.assertEqual(b[frame][physical_address(r,64,2,'nr_output')],expected[i])
                    else:
                        self.assertEqual(a[frame][physical_address(r,64,2,'nr_output')],vector[i])
                        self.assertEqual(b[frame][physical_address(i,64,2,'nr_input')],expected[i])
