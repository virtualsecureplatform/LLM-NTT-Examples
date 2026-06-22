import importlib.util
import math
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "compare_autontt_metrics.py"
SPEC = importlib.util.spec_from_file_location("compare_autontt_metrics", SCRIPT_PATH)
compare_autontt_metrics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(compare_autontt_metrics)


class AutoNttMetricCompareTests(unittest.TestCase):
    def test_compare_results_computes_latency_and_resource_scores(self):
        reference = {
            "task_id": "example_task",
            "correct": True,
            "vitis_synthesis_passed": True,
            "metrics": {
                "example_input_cycles": 10,
                "example_max_wait_cycles": 20,
                "example_output_cycles": 10,
                "vitis_lut": 100,
                "vitis_ff": 200,
                "vitis_dsp": 10,
                "vitis_bram_tile": 0,
                "vitis_uram": 0,
                "vitis_fmax_mhz": 250,
                "vitis_timing_wns_ns": 1.0,
            },
        }
        candidate = {
            "task_id": "example_task",
            "correct": True,
            "vitis_synthesis_passed": True,
            "metrics": {
                "example_input_cycles": 10,
                "example_max_wait_cycles": 10,
                "example_output_cycles": 10,
                "vitis_lut": 50,
                "vitis_ff": 100,
                "vitis_dsp": 5,
                "vitis_bram_tile": 0,
                "vitis_uram": 0,
                "vitis_fmax_mhz": 500,
                "vitis_timing_wns_ns": 2.5,
            },
        }

        comparison = compare_autontt_metrics.compare_results(reference, candidate)

        latency = comparison["latency"]["groups"]["example"]
        self.assertEqual(latency["reference"]["total_cycles"], 40)
        self.assertEqual(latency["candidate"]["total_cycles"], 30)
        self.assertAlmostEqual(latency["latency_score"], 40 / 30)
        self.assertAlmostEqual(
            comparison["latency"]["aggregate_latency_score"], 40 / 30
        )
        self.assertAlmostEqual(
            comparison["resources"]["metrics"]["vitis_lut"][
                "candidate_over_reference"
            ],
            0.5,
        )
        self.assertAlmostEqual(
            comparison["resources"]["memory"]["candidate_over_reference"], 1.0
        )
        self.assertAlmostEqual(comparison["resources"]["resource_penalty"], 0.575)
        self.assertAlmostEqual(
            comparison["resource_aware_score"], (40 / 30) / 0.575
        )
        self.assertAlmostEqual(
            comparison["timing"]["fmax_mhz"]["candidate_over_reference"], 2.0
        )
        self.assertAlmostEqual(
            comparison["timing"]["wns_ns"]["candidate_minus_reference"], 1.5
        )

    def test_compare_results_handles_multiple_latency_groups_with_geomean(self):
        reference = {
            "task_id": "yata",
            "correct": True,
            "metrics": {
                "ntt_input_cycles": 8,
                "ntt_max_wait_cycles": 35,
                "ntt_output_cycles": 8,
                "intt_input_cycles": 8,
                "intt_max_wait_cycles": 34,
                "intt_output_cycles": 8,
            },
        }
        candidate = {
            "task_id": "yata",
            "correct": True,
            "metrics": {
                "ntt_input_cycles": 8,
                "ntt_max_wait_cycles": 17,
                "ntt_output_cycles": 8,
                "intt_input_cycles": 8,
                "intt_max_wait_cycles": 16,
                "intt_output_cycles": 8,
            },
        }

        comparison = compare_autontt_metrics.compare_results(reference, candidate)

        ntt_score = 51 / 33
        intt_score = 50 / 32
        self.assertAlmostEqual(
            comparison["latency"]["aggregate_latency_score"],
            math.sqrt(ntt_score * intt_score),
        )

    def test_format_table_reports_unavailable_metrics(self):
        comparison = compare_autontt_metrics.compare_results(
            {"task_id": "smoke", "correct": True, "metrics": {"wait_cycles": 5}},
            {"task_id": "smoke", "correct": True, "metrics": {"wait_cycles": 5}},
        )

        table = compare_autontt_metrics.format_table(comparison)

        self.assertIn("Task: reference=smoke candidate=smoke match=True", table)
        self.assertIn("resource_penalty,n/a", table)


if __name__ == "__main__":
    unittest.main()
