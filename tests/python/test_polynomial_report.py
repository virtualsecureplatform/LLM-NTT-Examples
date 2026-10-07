import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.report_polynomial_study import combined_campaigns, METRICS


class CombinedStudyReportTests(unittest.TestCase):
    def write_campaign(self, folder, rows, corpus='same'):
        folder.mkdir()
        (folder/'results.json').write_text(json.dumps(dict(points=rows,coverage={},frontiers={})))
        (folder/'manifest.json').write_text(json.dumps(dict(spec=dict(n=512,error_limits=[8]),corpora={'full-full':corpus})))

    def row(self, name, value):
        return dict(name=name,workload_name='full-full',workload={'n':512},passed=True,
                    status='screened',**dict.fromkeys(METRICS,value))

    def test_duplicate_baseline_is_counted_once_and_frontier_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            old=self.row('old',10); better=self.row('new',5)
            old['max_abs_error']=better['max_abs_error']=0
            self.write_campaign(a,[old])
            self.write_campaign(b,[old,better])
            groups,provenance=combined_campaigns([a,b])
            self.assertEqual(len(groups[0][1]['points']),2)
            self.assertEqual(groups[0][1]['frontiers']['full-full']['0'],['new'])
            self.assertEqual(len(provenance),2)

    def test_incompatible_corpora_and_duplicate_measurements_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=Path(d)/'a',Path(d)/'b',Path(d)/'c'
            old=self.row('old',10)
            self.write_campaign(a,[old])
            self.write_campaign(b,[old],corpus='different')
            changed=copy.deepcopy(old);changed['yosys_cells']=11
            self.write_campaign(c,[changed])
            for other in (b,c):
                with self.assertRaises(ValueError):combined_campaigns([a,other])


if __name__=='__main__':unittest.main()
