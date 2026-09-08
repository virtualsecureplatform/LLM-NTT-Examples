import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from architecture_search.hardware import _evaluate
from architecture_search.model import evidence_integrity, frontier

class Integrity(unittest.TestCase):
    def test_measurement_and_artifact_drift(self):
        for mutation in ('none','rtl','memory','include-added','include-removed','metric','report'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);rtl=d/'top.sv';rtl.write_text('original')
                memory=d/'table.mem';memory.write_text('01')
                includes=d/'include';includes.mkdir();header=includes/'a.vh';header.write_text('original')
                def vendor(command, cwd, log, timeout):
                    output=Path(command[command.index('--metrics-json')+1])
                    output.write_text(json.dumps({'passed':True,'metrics':{'vitis_lut':10,'vitis_timing_wns_ns':1}}))
                    if mutation=='rtl':rtl.write_text('changed')
                    if mutation=='memory':memory.write_text('02')
                    if mutation=='include-added':(includes/'b.vh').write_text('new')
                    if mutation=='include-removed':header.unlink()
                    return {'returncode':0}
                with patch('architecture_search.hardware.run',side_effect=vendor):
                    result=_evaluate(rtl,'top',{}, {},d/'synthesis','synthesis',10,
                                     include_dirs=[includes],additional_inputs=[memory])
                if mutation in ('none','metric','report'):
                    self.assertEqual(evidence_integrity(result),'verified')
                else:self.assertFalse(result['passed'])
                if mutation=='metric':result['metrics']['lut']=0
                if mutation=='report':(d/'synthesis/metrics.json').write_text('{}')
                result['metrics']['bandwidth_capped_transforms_per_second']=1
                self.assertEqual(evidence_integrity(result),'verified' if mutation=='none' else 'invalid')
                record={'id':'a','correct':True,'mode':'functional','evidence':{'synthesis':result}}
                self.assertEqual(frontier([record],{'lut':'min'},'synthesis',{}),['a'] if mutation=='none' else [])

    def test_legacy_evidence_is_explicit(self):
        self.assertEqual(evidence_integrity({'passed':True}),'legacy-unverified')
