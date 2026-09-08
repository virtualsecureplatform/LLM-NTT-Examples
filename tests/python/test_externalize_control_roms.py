import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('externalize',ROOT/'scripts/externalize_control_roms.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Externalize(unittest.TestCase):
    def test_preserves_every_word_in_simulation(self):
        if not shutil.which('iverilog') or not shutil.which('vvp'):self.skipTest('Icarus required')
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);rtl=d/'rom.sv'
            original='''module rom(input [1:0] index,output [7:0] value);
localparam integer BUNDLE_COUNT=4;
reg [7:0] control_0_rom[0:BUNDLE_COUNT-1];
initial begin
control_0_rom[0]=8'h0;
control_0_rom[1]=8'hff;
control_0_rom[2]=8'ha5;
control_0_rom[3]=8'h5a;
end
assign value=control_0_rom[index];
endmodule
'''
            rtl.write_text(original);tb=d/'test.sv';tb.write_text('module test;reg [1:0] index;wire [7:0] value;integer i;rom dut(index,value);initial begin for(i=0;i<4;i=i+1)begin index=i;#1;$display("%h",value);end $finish;end endmodule')
            def simulate():
                subprocess.run(['iverilog','-g2012','-s','test','-o',str(d/'sim'),str(rtl),str(tb)],check=True,capture_output=True)
                return subprocess.check_output(['vvp',str(d/'sim')])
            before=simulate();records=module.externalize(rtl);after=simulate()
            self.assertEqual(before,after);self.assertEqual(records[0]['words'],4)
            self.assertEqual(Path(records[0]['path']).read_text().splitlines(),['00','ff','a5','5a'])

    def test_rejects_missing_addresses_without_replacing_rtl(self):
        with tempfile.TemporaryDirectory() as tmp:
            rtl=Path(tmp)/'rom.sv';source="module rom;\nreg [7:0] control_0_rom[0:BUNDLE_COUNT-1];\ncontrol_0_rom[0]=8'h0;\ncontrol_0_rom[2]=8'h1;\nendmodule\n";rtl.write_text(source)
            with self.assertRaisesRegex(ValueError,'contiguous'):module.externalize(rtl)
            self.assertEqual(rtl.read_text(),source)
