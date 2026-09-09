import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('output_hold_repair',ROOT/'scripts/repair_output_hold.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)


class OutputHoldRepair(unittest.TestCase):
    def test_reports_preserve_totals_negative_slack_and_route_completeness(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'utilization_route.rpt').write_text('| CLB LUTs | 1,112 | 0 |\n| CLB Registers | 44 | 0 |\n| CLB LUTs | 0 | 0 |\n')
            (d/'timing.properties').write_text('wns_ns=0.000\nhold_slack_ns=-0.017\nadded_output_luts=11\n')
            status=d/'route_status.rpt';status.write_text('# of routable nets.... : 10 :\n# of fully routed nets.... : 10 :\n# of nets with routing errors.... : 0 :\n')
            metrics,complete=repair.parse_reports(d)
            self.assertEqual(metrics['lut'],1112)
            self.assertEqual(metrics['hold_slack_ns'],-0.017)
            self.assertNotIn('dsp',metrics)
            self.assertTrue(complete)
            status.write_text(status.read_text().replace('fully routed nets.... : 10','fully routed nets.... : 9'))
            self.assertFalse(repair.parse_reports(d)[1])
            (d/'timing.properties').write_text('wns_ns=nan\nhold_slack_ns=inf\n')
            self.assertNotIn('wns_ns',repair.parse_reports(d)[0])
            self.assertNotIn('hold_slack_ns',repair.parse_reports(d)[0])

    def test_source_requires_integrity_and_nonnegative_measured_setup(self):
        evidence={'implementation_passed':True,'metrics':{'wns_ns':-0.001}}
        report={'candidates':[{'correct':True,'evidence':{'route':evidence}}]}
        with patch.object(repair,'evidence_integrity',return_value='invalid'):
            with self.assertRaisesRegex(ValueError,'integrity'):repair.validate_source(report)
        with patch.object(repair,'evidence_integrity',return_value='verified'):
            for slack in (-0.001,None,float('nan'),True):
                evidence['metrics']['wns_ns']=slack
                with self.subTest(slack=slack),self.assertRaisesRegex(ValueError,'setup'):repair.validate_source(report)
