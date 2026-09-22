from pathlib import Path
import random,shutil,subprocess,tempfile,unittest
from architecture_search import adapters,preloaded_ntt
ROOT=Path(__file__).resolve().parents[2]
class PreloadedTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp') and (ROOT/'third_party/NGen/ngen.bat').exists(),'generator and Icarus required')
    def test_storage_counters_both_directions_and_reset_recovery(self):
        w=dict(kind='generic',n=8,q='17',root='9',negacyclic=False,lanes=2)
        rng=random.Random(8);vectors=[[0]*8,[16]*8]+[[rng.randrange(17) for _ in range(8)] for _ in range(4)]
        for backend in ('streamed','stage-parallel'):
            with self.subTest(backend=backend),tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);parts=[]
                c=adapters.candidates(w,ROOT/'third_party/NGen',dict(backends=[backend],pe=[1],radix=[2],stage_groups=[1],reductions=['barrett'],profiles=['baseline']))[0]
                for direction in ('forward','inverse'):
                    process,rtl=adapters.generate(dict(w,direction=direction),c,ROOT/'third_party/NGen',d/direction,60)
                    self.assertEqual(process['returncode'],0)
                    parts.append(preloaded_ntt.namespace(rtl.read_text(),direction.title()))
                (d/'design.sv').write_text('\n'.join(parts+[preloaded_ntt.wrapper(w,2)]))
                for name,text in preloaded_ntt.fixtures(w,2,vectors).items():(d/name).write_text(text)
                (d/'test.sv').write_text(preloaded_ntt.testbench(w,2,vectors))
                subprocess.run(['iverilog','-g2012','-s','test','-o','simulation','design.sv','test.sv'],cwd=d,check=True,capture_output=True,timeout=60)
                result=subprocess.run(['vvp','simulation'],cwd=d,check=True,capture_output=True,text=True,timeout=60)
                self.assertIn('PASS preloaded transform',result.stdout)
