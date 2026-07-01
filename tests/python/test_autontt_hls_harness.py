import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_autontt_hls_harness.py"
SPEC = importlib.util.spec_from_file_location("run_autontt_hls_harness", SCRIPT_PATH)
harness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(harness)


class AutoNttHlsHarnessTests(unittest.TestCase):
    def test_default_arch_type_includes_dataflow(self):
        args = harness.build_arg_parser().parse_args([])

        self.assertEqual(args.arch_type, "ID")
        self.assertIn("D", harness.requested_arch_types(args.arch_type))

    def test_expected_design_prefixes_expand_combined_arch_type(self):
        args = SimpleNamespace(
            arch_type="ID",
            modmul_type="C",
            poly_size="1024",
            mod_size="64",
        )

        self.assertEqual(
            harness.expected_design_prefixes(args),
            [
                "AutoNTT_I__N_1024__q_64__red_CUSTOM_REDUCTION__",
                "AutoNTT_D__N_1024__q_64__red_CUSTOM_REDUCTION__",
            ],
        )

    def test_find_recent_design_dirs_matches_selected_arch_from_combined_filter(self):
        args = SimpleNamespace(
            arch_type="ID",
            modmul_type="B",
            poly_size="1024",
            mod_size="64",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tool_outputs = Path(tmpdir) / "tool_outputs"
            tool_outputs.mkdir()
            since = time.time() - 10

            stale_iterative = tool_outputs / (
                "AutoNTT_I__N_1024__q_64__red_BARRETT__BUs_64"
            )
            recent_dataflow = tool_outputs / (
                "AutoNTT_D__N_1024__q_64__red_BARRETT__BUG_4x2__BUs_40"
            )
            stale_iterative.mkdir()
            recent_dataflow.mkdir()
            old_time = since - 10
            os.utime(stale_iterative, (old_time, old_time))

            matches = harness.find_recent_design_dirs(
                tool_outputs,
                harness.expected_design_prefixes(args),
                since,
            )

        self.assertEqual(matches, [recent_dataflow])


if __name__ == "__main__":
    unittest.main()
