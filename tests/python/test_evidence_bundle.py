import json,tempfile,unittest
from pathlib import Path
from architecture_search.evidence_bundle import export,verify
class BundleTests(unittest.TestCase):
    def test_relocated_bundle_survives_deleted_original_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);artifact=root/'rtl.sv';artifact.write_text('module Top;endmodule')
            report=root/'report.json';report.write_text(json.dumps(dict(rtl_path=str(artifact))))
            result=export([report],root/'bundle');report.unlink();artifact.unlink()
            (root/'bundle').rename(root/'moved');self.assertTrue(verify(root/'moved')['verified'])
            (root/'moved'/'objects'/result['paths'][str(artifact)]).write_text('changed')
            with self.assertRaises(ValueError):verify(root/'moved')
