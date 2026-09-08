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
            fake.write_text(fake.read_text().replace('fully routed nets.... : 10','fully routed nets.... : 9'))
            self.assertNotEqual(subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).returncode,0)
            self.assertFalse(json.loads(output.read_text())['passed'])

    def test_vivado_queue_respects_timeout(self):
        import fcntl
        from architecture_search.hardware import evaluate
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            lock_path=Path(tmp)/f'ntt-search-vivado-{os.getuid()}.lock'
            with lock_path.open('a') as lock, patch('architecture_search.hardware.tempfile.gettempdir',return_value=tmp):
                fcntl.flock(lock,fcntl.LOCK_EX)
                result=evaluate(Path(tmp)/'unused.sv','unused',{}, {},Path(tmp),'route',0.03)
                self.assertFalse(result['passed'])
                self.assertEqual(result['error'],'Vivado queue timeout')
