import importlib.util
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_small_variant_hls_synth_compare.py"
SPEC = importlib.util.spec_from_file_location("run_small_variant_hls_synth_compare", SCRIPT_PATH)
small_hls = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(small_hls)


class SmallVariantHlsSynthCompareTests(unittest.TestCase):
    def test_declares_expected_variants(self):
        self.assertEqual(small_hls.VARIANTS["hoge32"].n, 32)
        self.assertEqual(small_hls.VARIANTS["hoge32"].cycles, 1)
        self.assertEqual(small_hls.VARIANTS["yata8"].n, 8)
        self.assertEqual(small_hls.VARIANTS["yata8"].cycles, 1)
        self.assertEqual(small_hls.VARIANTS["yata8x8"].n, 64)
        self.assertEqual(small_hls.VARIANTS["yata8x8"].lanes, 8)
        self.assertEqual(small_hls.VARIANTS["yata8x8"].cycles, 8)

    def test_yata_tables_scale_to_8_and_8x8(self):
        yata8 = small_hls.generate_yata_tables(3)
        yata64 = small_hls.generate_yata_tables(6)

        self.assertEqual(small_hls.YATA_R2, 15277344)
        self.assertEqual(len(yata8["YATA_INTT_TWIST"]), 8)
        self.assertEqual(len(yata64["YATA_INTT_TWIST"]), 64)
        self.assertEqual(yata8["YATA_INTT_TWIST"][0], small_hls.YATA_R)
        self.assertEqual(yata64["YATA_NTT_TABLE1"][0], small_hls.YATA_R2)

    def test_hoge32_tables_have_expected_root_progression(self):
        tables = small_hls.generate_hoge_tables(5)
        twist = pow(small_hls.HOGE_W, 1 << (32 - 5 - 1), small_hls.HOGE_P)

        self.assertEqual(len(tables["HOGE_INTT_TWIST"]), 32)
        self.assertEqual(tables["HOGE_INTT_TWIST"][0], 1)
        self.assertEqual(tables["HOGE_INTT_TWIST"][1], twist)
        self.assertEqual(tables["HOGE_INVN"][0], pow(32, -1, small_hls.HOGE_P))

    def test_generated_sources_include_reference_and_generated_tops(self):
        for name, variant in small_hls.VARIANTS.items():
            source = small_hls.generate_source(variant)
            self.assertIn(f"extern \"C\" void {name}_reference_intt_hls", source)
            self.assertIn(f"extern \"C\" void {name}_generated_intt_hls", source)
            self.assertIn(f"extern \"C\" void {name}_reference_ntt_hls", source)
            self.assertIn(f"extern \"C\" void {name}_generated_ntt_hls", source)
            self.assertIn(f"extern \"C\" void {name}_reference_hls", source)
            self.assertIn(f"extern \"C\" void {name}_generated_hls", source)

    def test_checked_in_reference_baselines_exist(self):
        for variant in small_hls.VARIANTS.values():
            baseline = small_hls.load_reference_baseline(
                variant, small_hls.DEFAULT_REFERENCE_BASELINE_DIR
            )
            self.assertIsNotNone(baseline)
            assert baseline is not None
            data, path = baseline
            self.assertEqual(path.name, f"{variant.task_id}.json")
            self.assertEqual(data["task_id"], variant.task_id)
            self.assertTrue(data["correct"])
            if "vitis_lut" in data.get("metrics", {}):
                self.assertTrue(data["vitis_synthesis_passed"])

    def test_build_results_maps_latency_and_resources(self):
        variant = small_hls.VARIANTS["yata8x8"]
        reports = {
            "intt": {
                "path": "/tmp/intt.xml",
                "worst_latency_cycles": 108,
                "resources": {},
            },
            "ntt": {
                "path": "/tmp/ntt.xml",
                "worst_latency_cycles": 208,
                "resources": {},
            },
            "combined": {
                "path": "/tmp/combined.xml",
                "worst_latency_cycles": 300,
                "estimated_clock_period_ns": 2.5,
                "resources": {"LUT": 11, "FF": 13, "DSP": 17, "BRAM_18K": 19, "URAM": 23},
            },
        }

        result = small_hls.build_results(
            variant,
            "generated",
            reports,
            4.0,
            "part",
            {},
            "source.cpp",
        )

        metrics = result["metrics"]
        self.assertEqual(result["task_id"], "small_yata8x8_raintt_p27")
        self.assertEqual(metrics["small_yata8x8_raintt_p27_intt_input_cycles"], 8)
        self.assertEqual(metrics["small_yata8x8_raintt_p27_intt_max_wait_cycles"], 92)
        self.assertEqual(metrics["small_yata8x8_raintt_p27_ntt_max_wait_cycles"], 192)
        self.assertEqual(metrics["vitis_lut"], 11)
        self.assertEqual(metrics["vitis_bram_tile"], 19)
        self.assertAlmostEqual(metrics["vitis_fmax_mhz"], 400.0)
        self.assertAlmostEqual(metrics["vitis_timing_wns_ns"], 1.5)


if __name__ == "__main__":
    unittest.main()
