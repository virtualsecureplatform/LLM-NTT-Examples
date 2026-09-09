import tempfile
import unittest
from pathlib import Path
from architecture_search.oracle import transform
from scripts.capture_seal_ntt_trace import natural_order,verify_samples

class SealSamples(unittest.TestCase):
    def test_bit_reversal_is_correct_and_involutive(self):
        self.assertEqual(natural_order(list(range(8))),[0,4,2,6,1,5,3,7])
        self.assertEqual(natural_order(natural_order(list(range(8)))),list(range(8)))
    def test_lazy_representatives_both_directions_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);w={'n':8,'q':'17','psi':'3','root':'9','negacyclic':True,'direction':'forward'}
            a=list(range(8));b=transform(a,w,direct=True);events=[]
            for direction,inputs,outputs in [('forward',a,natural_order(b)),('inverse',natural_order(b),a)]:
                events.append({**w,'direction':direction})
                (directory/f'8_17_{direction}.txt').write_text(''.join(f'{x+17} {y+34}\n' for x,y in zip(inputs,outputs)))
            self.assertEqual(len(verify_samples(directory,events)),2)
            p=directory/'8_17_forward.txt';rows=p.read_text().splitlines();x,y=map(int,rows[2].split());rows[2]=f'{x} {y+1}';p.write_text('\n'.join(rows)+'\n')
            with self.assertRaisesRegex(ValueError,'mismatch'):verify_samples(directory,events)
