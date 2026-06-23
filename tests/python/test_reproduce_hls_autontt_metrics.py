import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "reproduce_hls_autontt_metrics.py"
SPEC = importlib.util.spec_from_file_location("reproduce_hls_autontt_metrics", SCRIPT_PATH)
repro = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(repro)


class ReproduceHlsAutoNttMetricsTests(unittest.TestCase):
    def test_parse_targets(self):
        self.assertEqual(repro.parse_targets("all"), ["small", "full-yata"])
        self.assertEqual(repro.parse_targets("small"), ["small"])
        self.assertEqual(repro.parse_targets("small,full-yata"), ["small", "full-yata"])
        with self.assertRaises(Exception):
            repro.parse_targets("unknown")

    def test_resolve_sif_auto_prefers_env_then_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"LLM_NTT_SIF": "/tmp/custom.sif"}):
            self.assertEqual(repro.resolve_sif("auto"), Path("/tmp/custom.sif"))

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(Path, "exists", return_value=False):
                self.assertEqual(
                    repro.resolve_sif("auto"),
                    REPO_ROOT / "llm-ntt.sif",
                )

    def test_top_rtl_dirs_from_results(self):
        data = {
            "hls_reports": {
                "intt": "build/example/proj/solution1/syn/report/top_csynth.xml",
                "note": "not-a-report.txt",
            }
        }

        dirs = repro.top_rtl_dirs_from_results(data)

        self.assertEqual(len(dirs), 1)
        self.assertEqual(dirs[0], REPO_ROOT / "build/example/proj/solution1/syn/verilog")

    def test_build_report_summarizes_comparison(self):
        comparison = {
            "task_id": {"candidate": "small_hoge32_p64"},
            "latency": {
                "groups": {
                    "small_hoge32_p64_intt": {"candidate": {"total_cycles": 10}},
                    "small_hoge32_p64_ntt": {"candidate": {"total_cycles": 12}},
                }
            },
            "resources": {
                "metrics": {
                    "vitis_lut": {"candidate": 1},
                    "vitis_ff": {"candidate": 2},
                    "vitis_dsp": {"candidate": 3},
                    "vitis_bram_tile": {"candidate": 4},
                    "vitis_uram": {"candidate": 5},
                }
            },
            "timing": {"fmax_mhz": {"candidate": 250.0}},
            "resource_aware_score": 0.5,
        }
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "build") as tmpdir:
            tmp = Path(tmpdir)
            comparison_path = tmp / "comparison.json"
            repro.write_json(comparison_path, comparison)
            summary = {"comparison": repro.relpath(comparison_path)}

            report = repro.build_report(
                run_root=tmp,
                sif=REPO_ROOT / "llm-ntt.sif",
                summaries=[summary],
                rtl_dirs=["build/example/proj/solution1/syn/verilog"],
            )

        self.assertIn("small_hoge32_p64", report)
        self.assertIn("| `small_hoge32_p64` | 10 | 12 | 1 | 2 | 3 | 4 | 5 | 250 | 0.5 |", report)
        self.assertIn("build/example/proj/solution1/syn/verilog", report)


if __name__ == "__main__":
    unittest.main()
