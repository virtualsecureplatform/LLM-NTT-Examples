import importlib.util
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_yata_hls_synth_compare.py"
SPEC = importlib.util.spec_from_file_location("run_yata_hls_synth_compare", SCRIPT_PATH)
yata_hls = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(yata_hls)


class YataHlsSynthCompareTests(unittest.TestCase):
    def test_generated_tables_match_known_raintt_constants(self):
        tables = yata_hls.generate_tables()

        self.assertEqual(yata_hls.R2, 15277344)
        self.assertEqual(
            tables["INTT_TWIST"][:8],
            [11337725, 35750749, 31736474, 38993454, 31828891, 32244917, 32702259, 40194565],
        )
        self.assertEqual(
            tables["NTT_TWIST"][:8],
            [262144, 30657314, 32662247, 38049329, 7666657, 17287720, 29398159, 37107061],
        )

    def test_generated_hls_source_has_yata_tops(self):
        source = yata_hls.generate_hls_source()

        self.assertIn("static const int32_t YATA_R2 = 15277344;", source)
        self.assertIn("extern \"C\" void yata_raintt_intt_hls", source)
        self.assertIn("extern \"C\" void yata_raintt_ntt_hls", source)
        self.assertIn("extern \"C\" void yata_raintt_hls", source)

    def test_parse_csynth_report_reads_latency_clock_and_resources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "top_csynth.xml"
            report.write_text(
                """\
<profile>
  <PerformanceEstimates>
    <SummaryOfTimingAnalysis>
      <EstimatedClockPeriod>3.017</EstimatedClockPeriod>
    </SummaryOfTimingAnalysis>
    <SummaryOfOverallLatency>
      <Best-caseLatency>12</Best-caseLatency>
      <Worst-caseLatency>34</Worst-caseLatency>
    </SummaryOfOverallLatency>
  </PerformanceEstimates>
  <AreaEstimates>
    <Resources>
      <BRAM_18K>2</BRAM_18K>
      <DSP>3</DSP>
      <FF>5</FF>
      <LUT>7</LUT>
      <URAM>0</URAM>
    </Resources>
  </AreaEstimates>
</profile>
""",
                encoding="utf-8",
            )

            parsed = yata_hls.parse_csynth_report(report)

        self.assertEqual(parsed["best_latency_cycles"], 12)
        self.assertEqual(parsed["worst_latency_cycles"], 34)
        self.assertEqual(parsed["estimated_clock_period_ns"], 3.017)
        self.assertEqual(parsed["resources"]["LUT"], 7)

    def test_build_candidate_results_maps_hls_reports_to_autontt_metrics(self):
        intt = {
            "best_latency_cycles": 10,
            "worst_latency_cycles": 116,
            "estimated_clock_period_ns": 2.9,
            "resources": {},
        }
        ntt = {
            "best_latency_cycles": 20,
            "worst_latency_cycles": 216,
            "estimated_clock_period_ns": 3.0,
            "resources": {},
        }
        combined = {
            "best_latency_cycles": 30,
            "worst_latency_cycles": 332,
            "estimated_clock_period_ns": 3.2,
            "resources": {"LUT": 11, "FF": 13, "DSP": 17, "BRAM_18K": 19, "URAM": 23},
        }

        result = yata_hls.build_candidate_results(
            intt_report=intt,
            ntt_report=ntt,
            combined_report=combined,
            clock_period_ns=4.0,
            part="part",
            logs={},
            generated_sources={},
            hls_reports={},
        )

        metrics = result["metrics"]
        self.assertEqual(result["task_id"], "yata_raintt_512_p27")
        self.assertTrue(result["correct"])
        self.assertTrue(result["vitis_synthesis_passed"])
        self.assertEqual(metrics["yata_raintt_intt_max_wait_cycles"], 100)
        self.assertEqual(metrics["yata_raintt_ntt_max_wait_cycles"], 200)
        self.assertEqual(metrics["vitis_lut"], 11)
        self.assertEqual(metrics["vitis_ff"], 13)
        self.assertEqual(metrics["vitis_dsp"], 17)
        self.assertEqual(metrics["vitis_bram_tile"], 19)
        self.assertEqual(metrics["vitis_uram"], 23)
        self.assertAlmostEqual(metrics["vitis_fmax_mhz"], 312.5)
        self.assertAlmostEqual(metrics["vitis_timing_wns_ns"], 0.8)


if __name__ == "__main__":
    unittest.main()
