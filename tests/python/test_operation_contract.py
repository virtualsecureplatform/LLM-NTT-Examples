"""Independent negative checks of the lowered-RTL qualification boundary."""
import copy
import tempfile
import unittest
import shutil
from unittest.mock import patch
from pathlib import Path
from architecture_search.operation_contract import audit, decode
from architecture_search.model import file_hash
from architecture_search import primitive_proofs, product_rtl


def example():
    nodes=[dict(id=0,op='Input',width=8,signal='a',inputs=[]),
           dict(id=1,op='Input',width=8,signal='b',inputs=[]),
           dict(id=2,op='Times',width=16,signal='s1',inputs=[0,1],signed=True),
           dict(id=3,op='Tap',width=8,signal='s2',inputs=[2],low=6,high=13),
           dict(id=4,op='Output',width=8,signal='result',inputs=[3])]
    return dict(schema='sgen-lowered-operations-v1',nodes=nodes,inputs=[0,1],outputs=[4])


class OperationContracts(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'core.v'
        self.contract=example()
        source,_=decode(self.contract,'test');self.path.write_text(source)
        self.meta=dict(operation_contract=self.contract,top='test',integer_bits=4,
                       fractional_bits=4,twiddle_fractional_bits=6,rtl_sha256=file_hash(self.path))

    def test_complete_correspondence(self):
        result=audit(self.meta,self.path)
        self.assertTrue(result['passed']);self.assertEqual(result['multiply_count'],1)

    def test_rehashed_rtl_mutations_still_fail(self):
        original=self.path.read_text()
        for source in (original.replace('$signed(a)','$unsigned(a)'),
                       original.replace('[13:6]','[12:5]'),
                       original.replace('a) *','b) *'),
                       original.replace('endmodule','assign result=0;\nendmodule')):
            self.path.write_text(source);self.meta['rtl_sha256']=file_hash(self.path)
            with self.assertRaises(ValueError):audit(self.meta,self.path)

    def test_descriptor_mutations_fail(self):
        for change in (dict(signed=False),dict(width=15),dict(inputs=[0,99])):
            contract=copy.deepcopy(self.contract);contract['nodes'][2].update(change)
            with self.assertRaises(ValueError):decode(contract,'test')

    def test_self_consistent_wrong_truncation_is_not_certifiable(self):
        contract=copy.deepcopy(self.contract);contract['nodes'][3].update(low=5,high=12)
        self.path.write_text(decode(contract,'test')[0])
        self.meta.update(operation_contract=contract,rtl_sha256=file_hash(self.path))
        with self.assertRaisesRegex(ValueError,'truncate'):audit(self.meta,self.path)

    def test_unsupported_operator_is_not_silently_ignored(self):
        self.contract['nodes'][2]['op']='ExternalMultiplier'
        with self.assertRaises(ValueError):decode(self.contract,'test')


@unittest.skipUnless(shutil.which('yosys'),'Yosys 0.50 is required for primitive proof tests')
class ActualWidthProofs(unittest.TestCase):
    def test_pipeline_and_negative_truncation_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertTrue(primitive_proofs.prove_pointwise(48,24,root/'good')['passed'])
            emit=product_rtl.multiply_module
            def mutated(*args):return emit(*args).replace('[24 +: 48]','[23 +: 48]')
            with patch.object(product_rtl,'multiply_module',side_effect=mutated):
                self.assertFalse(primitive_proofs.prove_pointwise(48,24,root/'bad')['passed'])

    def test_signed_ties_to_even_and_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertTrue(primitive_proofs.prove_rounding(16,48,24,11,root/'good')['passed'])
            emit=product_rtl.fold_module
            with patch.object(product_rtl,'fold_module',side_effect=lambda *a:emit(*a).replace('&& base[0]','&& !base[0]')):
                self.assertFalse(primitive_proofs.prove_rounding(16,48,24,11,root/'bad')['passed'])


if __name__=='__main__':unittest.main()
