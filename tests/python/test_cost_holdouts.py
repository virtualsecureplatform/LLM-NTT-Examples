import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('holdouts',Path(__file__).resolve().parents[2]/'scripts/validate_cost_holdouts.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CostHoldouts(unittest.TestCase):
    def samples(self):
        return [{'configuration':{'generator':'ngen','backend':'streamed','radix':2,'pe':p,'stage_groups':g},
                 'rtl_hash':f'{p}-{g}','metrics':{'lut':100+20*g+30*p*g}} for p in (1,2,4) for g in (1,2)]

    def test_complete_level_is_excluded_and_unavailable_is_not_zero_error(self):
        folds=module.holdouts(self.samples())
        for fold in folds:
            self.assertFalse(set(fold['training_rtl_hashes'])&set(fold['held_out_rtl_hashes']))
            error=fold['methods']['structural']['errors']['lut']
            if fold['axis']=='pe':
                self.assertEqual(error['predicted'],2)
                self.assertAlmostEqual(error['mean_absolute_error'],0,places=8)
            else:
                self.assertEqual(error['predicted'],0)
                self.assertIsNone(error['mean_absolute_error'])

    def test_duplicate_artifact_cannot_leak_between_folds(self):
        samples=self.samples();samples[-1]['rtl_hash']=samples[0]['rtl_hash']
        with self.assertRaisesRegex(ValueError,'overlap'):module.holdouts(samples)
