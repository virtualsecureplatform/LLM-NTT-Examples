"""Exercise report ingestion with whole-device totals followed by repeated SLR rows."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class Reports(unittest.TestCase):
    def test_device_totals_survive_slr_tables_and_route_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);fake=d/'vivado';rtl=d/'top.sv';rtl.write_text('module top(input clock); endmodule')
            fake.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
a=sys.argv[sys.argv.index('-tclargs')+1:]
Path(a[8]).write_text('| CLB LUTs | 1112 | 0 | 0 | 1303680 | 0.09 |\\n| CLB Registers | 442 | 0 | 0 | 2607360 | 0.02 |\\n| CLB LUTs | 0 | 0 | 0 | 100 | 0 |\\n| CLB Registers | 0 | 0 | 0 | 100 | 0 |\\n')
Path(a[9]).write_text('timing')
Path(a[10]).write_text('vitis_timing_wns_ns=0.2\\nvitis_hold_slack_ns=0.1\\n')
Path(a[11]).write_text('checkpoint')
Path(a[6],'route_status.rpt').write_text('# of routable nets.... : 10 :\\n# of fully routed nets.... : 10 :\\n# of nets with routing errors.... : 0 :\\n')
''');fake.chmod(0o755)
            output=d/'metrics.json'
            command=['bash',str(ROOT/'scripts/vitis_synth_rtl.sh'),'--stage','route','--top','top','--verilog-file',str(rtl),'--build-dir',str(d/'build'),'--metrics-json',str(output),'--vivado-bin',str(fake)]
            subprocess.run(command,cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            result=json.loads(output.read_text())
            self.assertTrue(result['passed']);self.assertTrue(result['route_complete'])
            self.assertEqual(result['metrics']['vitis_lut'],1112)
            self.assertEqual(result['metrics']['vitis_ff'],442)
            from architecture_search.hardware import _evaluate
            measured=_evaluate(rtl,'top',{'vivado':str(fake),'output_hold_buffer_stages':2,'input_hold_buffer_stages':2}, {},d/'snapshot-build','route',10)
            self.assertTrue(measured['implementation_passed'])
            self.assertTrue(measured['passed'])
            measured_command=measured['process']['command']
            self.assertEqual(measured_command[measured_command.index('--output-hold-buffer-stages')+1],'2')
            self.assertEqual(measured_command[measured_command.index('--input-hold-buffer-stages')+1],'2')
            self.assertTrue((d/'snapshot-build-driver/scripts/insert_input_hold_buffers.tcl').is_file())
            self.assertTrue((d/'snapshot-build-driver/scripts/vitis_synth_rtl.sh').is_file())
            fake.write_text(fake.read_text().replace('fully routed nets.... : 10','fully routed nets.... : 9'))
            self.assertNotEqual(subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).returncode,0)
            self.assertFalse(json.loads(output.read_text())['passed'])

    def test_driver_is_snapshotted_before_vendor_execution(self):
        from architecture_search.hardware import _evaluate
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'synthesis'
            def inspect(command, cwd, log, timeout):
                script=Path(command[1])
                self.assertNotEqual(script,ROOT/'scripts/vitis_synth_rtl.sh')
                self.assertEqual(script.read_bytes(),(ROOT/'scripts/vitis_synth_rtl.sh').read_bytes())
                self.assertEqual((script.parent/'insert_output_hold_buffers.tcl').read_bytes(),
                                 (ROOT/'scripts/insert_output_hold_buffers.tcl').read_bytes())
                return {'returncode':1}
            with patch('architecture_search.hardware.run',side_effect=inspect):
                result=_evaluate(Path(tmp)/'top.sv','top',{}, {},directory,'synthesis',10)
            self.assertFalse(result['implementation_passed'])

    def test_vivado_queue_respects_timeout(self):
        import fcntl
        import time
        from architecture_search.hardware import evaluate
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            lock_path=Path(tmp)/f'ntt-search-vivado-{os.getuid()}.lock'
            with lock_path.open('a') as lock, patch('architecture_search.hardware.tempfile.gettempdir',return_value=tmp), patch('architecture_search.hardware._evaluate') as vendor:
                fcntl.flock(lock,fcntl.LOCK_EX)
                started=time.monotonic()
                result=evaluate(Path(tmp)/'unused.sv','unused',{}, {},Path(tmp),'route',0.03)
                self.assertFalse(result['passed'])
                self.assertEqual(result['error'],'Vivado queue timeout')
                self.assertGreaterEqual(result['queue_seconds'],0.03)
                self.assertLessEqual(result['queue_seconds'],time.monotonic()-started)
                vendor.assert_not_called()
