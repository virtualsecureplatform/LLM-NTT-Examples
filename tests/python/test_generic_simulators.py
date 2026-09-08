import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from architecture_search import adapters,oracle
from architecture_search.evaluate import evaluate_generic,generic_simulator
from architecture_search.model import file_hash

class GenericSimulators(unittest.TestCase):
    def test_auto_selection_and_invalid_override(self):
        self.assertEqual(generic_simulator({'n':256},'auto'),'iverilog')
        self.assertEqual(generic_simulator({'n':16384},'auto'),'verilator')
        self.assertEqual(generic_simulator({'n':131072},'iverilog'),'iverilog')
        with self.assertRaises(ValueError):generic_simulator({'n':256},'unknown')

    def test_both_simulators_pass_full_oracle_without_changing_hardware_rtl(self):
        ngen=ROOT.parent/'NGen'
        if not (ngen/'ngen.bat').exists() or any(not shutil.which(tool) for tool in ('iverilog','vvp','verilator')):
            self.skipTest('built NGen, Icarus and Verilator required')
        w={'kind':'generic',**oracle.field(32,16),'direction':'forward','negacyclic':True,'lanes':4}
        config=adapters.candidates(w,ngen,{'pe':[2],'radix':[2],'stage_groups':[1],'reductions':['montgomery']})[0]
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);generation,rtl=adapters.generate(w,config,ngen,directory/'generated',60)
            self.assertEqual(generation['returncode'],0)
            original=file_hash(rtl)
            results=[evaluate_generic(w,config,rtl,directory/tool,180,simulator=tool) for tool in ('iverilog','verilator')]
            self.assertTrue(all(r['correct'] for r in results))
            self.assertEqual(results[0]['metrics'],results[1]['metrics'])
            self.assertEqual(file_hash(rtl),original)
            self.assertEqual(len(results[1]['externalized_control_roms']),2)
            for result in results:
                self.assertTrue(result['inputs_unchanged'])
