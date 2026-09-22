from pathlib import Path
import shutil,subprocess,tempfile,unittest
from scripts.product_board import select
from architecture_search import products
ROOT=Path(__file__).resolve().parents[2]
class BoardTests(unittest.TestCase):
    def test_missing_verified_pair_is_rejected(self):
        with self.assertRaises(ValueError):select(dict(workload=products.workload(64),candidates=[]))
    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
    def test_batches_backpressure_and_counters(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'test'
            subprocess.run(['iverilog','-g2012','-s','test','-o',str(exe),str(ROOT/'board/product_stream.sv'),str(ROOT/'tests/rtl/product_stream_tb.sv')],check=True,capture_output=True,timeout=30)
            subprocess.run(['vvp',str(exe)],check=True,capture_output=True,timeout=30)
