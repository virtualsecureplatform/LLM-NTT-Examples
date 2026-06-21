import unittest
from pathlib import Path

from examples.autontt.llm_rtl_generator.autontt_space import generate_search_points
from examples.autontt.llm_rtl_generator.prompting import (
    extract_module_declaration,
    extract_verilog,
    require_module,
)


class LlmRtlGeneratorTests(unittest.TestCase):
    def test_extract_verilog_from_fence(self):
        text = "Here is code:\n```verilog\nmodule Foo();\nendmodule\n```\n"
        verilog = extract_verilog(text)
        self.assertEqual(verilog, "module Foo();\nendmodule\n")
        require_module(verilog, "Foo")

    def test_search_points_include_hoge_custom_reduction(self):
        task = {
            "parameters": {
                "N": 1024,
                "word_bits": 64,
                "lanes": 32,
                "radix": 32,
                "modulus_hex": "0xffffffff00000001",
            }
        }
        points = generate_search_points(task, arch_types="I", modmul_types="AUTO")
        self.assertEqual(points[0]["modmul_type"], "C")
        self.assertIsNotNone(points[0]["autontt_command"])

    def test_extract_module_declaration(self):
        path = Path(__file__).with_suffix(".tmp.v")
        try:
            path.write_text(
                "module Helper(); endmodule\n"
                "module Top(\n"
                "  input clock,\n"
                "  output [7:0] io_out\n"
                ");\n"
                "endmodule\n",
                encoding="utf-8",
            )
            decl = extract_module_declaration(path, "Top")
            self.assertIn("module Top(", decl)
            self.assertIn("output [7:0] io_out", decl)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
