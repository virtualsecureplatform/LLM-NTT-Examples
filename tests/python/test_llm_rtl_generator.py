import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from examples.autontt.llm_rtl_generator.autontt_space import generate_search_points
from examples.autontt.llm_rtl_generator.behavioral_hoge import (
    generate_hoge_externalproduct_behavioral,
    generate_hoge_nttid_behavioral,
    generate_hoge_streaming_intt_behavioral,
    generate_hoge_streaming_ntt_interface_behavioral,
)
from examples.autontt.llm_rtl_generator.behavioral_yata import (
    generate_yata_raintt_behavioral,
)
from examples.autontt.llm_rtl_generator.hardware_feedback import (
    analyze_rtl_for_hardware,
    summarize_vitis_log,
)
from examples.autontt.llm_rtl_generator.prompting import (
    extract_module_declaration,
    extract_verilog,
    require_module,
    validate_candidate,
)
from examples.autontt.llm_rtl_generator.runner import (
    LAB_ENDPOINT_ENV,
    build_chisel_generator_selection_messages,
    build_generator_selection_messages,
    copy_reference_candidate,
    normalize_endpoint,
    parse_behavioral_generator_selection,
    parse_chisel_generator_selection,
    redact_endpoint_urls,
    run_evaluator,
    write_behavioral_candidate,
    write_chisel_reference_candidate,
)


class LlmRtlGeneratorTests(unittest.TestCase):
    def test_extract_verilog_from_fence(self):
        text = "Here is code:\n```verilog\nmodule Foo();\nendmodule\n```\n"
        verilog = extract_verilog(text)
        self.assertEqual(verilog, "module Foo();\nendmodule\n")
        require_module(verilog, "Foo")

    def test_require_module_rejects_unclosed_module(self):
        with self.assertRaises(ValueError):
            require_module("module Foo();\n", "Foo")

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

    def test_normalize_endpoint(self):
        self.assertEqual(
            normalize_endpoint("http://example.test:8080"),
            "http://example.test:8080/v1",
        )
        self.assertEqual(
            normalize_endpoint("https://example.test/v1"),
            "https://example.test/v1",
        )

    def test_lab_endpoint_is_environment_backed(self):
        with patch.dict("os.environ", {LAB_ENDPOINT_ENV: ""}, clear=False):
            with self.assertRaises(ValueError):
                normalize_endpoint("lab")
        with patch.dict(
            "os.environ", {LAB_ENDPOINT_ENV: "http://example.test:9000"}, clear=False
        ):
            self.assertEqual(normalize_endpoint("lab"), "http://example.test:9000/v1")

    def test_redact_endpoint_urls(self):
        text = "http://private.example/v1/models request failed"
        self.assertEqual(
            redact_endpoint_urls(text),
            "<endpoint> request failed",
        )

    def test_copy_reference_candidate(self):
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            reference = repo_root / "variants" / "example" / "Top.v"
            reference.parent.mkdir(parents=True)
            reference.write_text("module Top(); endmodule\n", encoding="utf-8")
            attempt_dir = repo_root / "build" / "attempt"
            attempt_dir.mkdir(parents=True)
            task = {
                "verilog": {
                    "default_path": "variants/example/Top.v",
                    "candidate_file": "CandidateTop.v",
                }
            }

            candidate = copy_reference_candidate(
                repo_root, task, attempt_dir, "CandidateTop.v"
            )

            self.assertEqual(candidate, attempt_dir / "CandidateTop.v")
            self.assertEqual(
                candidate.read_text(encoding="utf-8"),
                reference.read_text(encoding="utf-8"),
            )

    def test_vitis_with_sif_uses_host_wrapper(self):
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_file = repo_root / "tasks" / "task.json"
            task_file.parent.mkdir()
            candidate_dir = repo_root / "candidate"
            build_dir = repo_root / "build"
            results_file = build_dir / "results.json"
            sif = repo_root / "llm-ntt.sif"

            with patch(
                "examples.autontt.llm_rtl_generator.runner.subprocess.run"
            ) as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""

                run_evaluator(
                    repo_root=repo_root,
                    task_file=task_file,
                    candidate_dir=candidate_dir,
                    build_dir=build_dir,
                    results_file=results_file,
                    with_yosys=False,
                    with_vitis=True,
                    vitis_part="xcu280-fsvh2892-2L-e",
                    vitis_clock_period="4.0",
                    vitis_clock_port="clock",
                    vitis_jobs="2",
                    vivado_bin="vivado",
                    xilinx_settings="",
                    apptainer_bin="apptainer",
                    sif=sif,
                )

            cmd = run.call_args.args[0]
            self.assertEqual(
                cmd[0], str(repo_root / "scripts" / "evaluate_with_apptainer_and_vitis.sh")
            )
            self.assertIn("--sif", cmd)
            self.assertIn("--vitis-timeout", cmd)
            self.assertNotIn("exec", cmd[:4])

    def test_vitis_without_sif_uses_candidate_evaluator(self):
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_file = repo_root / "tasks" / "task.json"
            task_file.parent.mkdir()
            candidate_dir = repo_root / "candidate"
            build_dir = repo_root / "build"
            results_file = build_dir / "results.json"

            with patch(
                "examples.autontt.llm_rtl_generator.runner.subprocess.run"
            ) as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""

                run_evaluator(
                    repo_root=repo_root,
                    task_file=task_file,
                    candidate_dir=candidate_dir,
                    build_dir=build_dir,
                    results_file=results_file,
                    with_yosys=False,
                    with_vitis=True,
                    vitis_part="xcu280-fsvh2892-2L-e",
                    vitis_clock_period="4.0",
                    vitis_clock_port="clock",
                    vitis_jobs="2",
                    vivado_bin="vivado",
                    xilinx_settings="",
                    sif=None,
                )

            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0], str(repo_root / "scripts" / "evaluate_candidate.sh"))
            self.assertIn("--with-vitis", cmd)
            self.assertIn("--vitis-part", cmd)
            self.assertIn("--vitis-timeout", cmd)

    def test_hoge_behavioral_generator_validates(self):
        task = {
            "id": "hoge_streaming_intt_1024_p64",
            "top_module": "INTTWrap",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 1024},
        }
        verilog = generate_hoge_streaming_intt_behavioral()

        validate_candidate(verilog, task)
        self.assertIn("module INTTWrap(", verilog)
        self.assertIn("task compute_transform", verilog)

    def test_hoge_identity_behavioral_generator_validates(self):
        task = {
            "id": "hoge_nttid_1024_identity",
            "top_module": "NTTidPackedTop",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 1024},
            "reference": {"operation": "identity modulo P"},
        }
        verilog = generate_hoge_nttid_behavioral()

        validate_candidate(verilog, task)
        self.assertIn("assign io_out = io_in;", verilog)

    def test_hoge_ntt_interface_behavioral_generator_validates(self):
        task = {
            "id": "hoge_streaming_ntt_1024_p64",
            "top_module": "NTTWrap",
            "evaluation": {"mode": "lint_only"},
            "parameters": {"N": 1024},
        }
        verilog = generate_hoge_streaming_ntt_interface_behavioral()

        validate_candidate(verilog, task)
        self.assertIn("assign io_ready = 1'b1;", verilog)

    def test_hoge_externalproduct_behavioral_generator_validates(self):
        task = {
            "id": "hoge_externalproduct_ntt_1024_p64",
            "top_module": "ExternalProductWrap",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 1024},
        }
        verilog = generate_hoge_externalproduct_behavioral()

        validate_candidate(verilog, task)
        self.assertIn("module ExternalProductWrap(", verilog)
        self.assertIn("task automatic compute_externalproduct", verilog)
        self.assertIn("assign io_trgswinready", verilog)

    def test_yata_behavioral_generator_validates(self):
        task = {
            "id": "yata_raintt_512_p27",
            "top_module": "YataRainttTop",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 512},
        }
        verilog = generate_yata_raintt_behavioral()

        validate_candidate(verilog, task)
        self.assertIn("module YataRainttTop(", verilog)
        self.assertIn("task compute_intt", verilog)
        self.assertIn("task compute_ntt", verilog)
        self.assertIn("64'sd7036874245", verilog)

    def test_hardware_screen_rejects_full_transform_task_loops(self):
        task = {
            "id": "yata_raintt_512_p27",
            "top_module": "YataRainttTop",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 512, "lanes": 64},
        }
        verilog = generate_yata_raintt_behavioral()

        analysis = analyze_rtl_for_hardware(
            verilog,
            task,
            {"butterfly_budget": 8},
        )

        self.assertFalse(analysis["passed"])
        self.assertGreaterEqual(analysis["metrics"]["large_for_loop_count"], 1)
        self.assertGreaterEqual(analysis["metrics"]["transform_task_count"], 1)

    def test_hardware_screen_allows_simple_staged_shell(self):
        task = {
            "id": "yata_raintt_512_p27",
            "top_module": "YataRainttTop",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 512, "lanes": 64},
        }
        verilog = (
            "module YataRainttTop(input clock, input reset, output reg valid);\n"
            "  reg [8:0] coeff_idx;\n"
            "  always @(posedge clock) begin\n"
            "    if (reset) coeff_idx <= 0;\n"
            "    else coeff_idx <= coeff_idx + 1'b1;\n"
            "  end\n"
            "endmodule\n"
        )

        analysis = analyze_rtl_for_hardware(
            verilog,
            task,
            {"butterfly_budget": 8},
        )

        self.assertTrue(analysis["passed"])

    def test_summarize_vitis_log_extracts_dsp_pressure(self):
        summary = summarize_vitis_log(
            "DSP resource Status: x: Rejected (21181 > 9024)\n"
            "DSP resource Status: y: Accepted (9024 < 9024)\n"
            "Start Timing Optimization\n"
        )

        self.assertEqual(summary["dsp_rejected_count"], 1)
        self.assertEqual(summary["max_rejected_dsp_count"], 21181)
        self.assertTrue(summary["timing_optimization_started"])

    def test_write_behavioral_candidate(self):
        with TemporaryDirectory() as tmp:
            attempt_dir = Path(tmp)
            task = {
                "id": "hoge_streaming_intt_1024_p64",
                "top_module": "INTTWrap",
            }

            candidate = write_behavioral_candidate(task, attempt_dir, "INTTWrap.v")

            self.assertEqual(candidate, attempt_dir / "INTTWrap.v")
            require_module(candidate.read_text(encoding="utf-8"), "INTTWrap")

    def test_build_generator_selection_messages(self):
        task = {
            "id": "hoge_streaming_intt_1024_p64",
            "name": "HOGE streaming 1024-point INTT",
            "top_module": "INTTWrap",
            "parameters": {"N": 1024},
            "evaluation": {"mode": "verilator_test"},
        }
        messages = build_generator_selection_messages(
            task_file=Path("tasks/hoge_streaming_intt_1024_p64.json"),
            task=task,
            search_point={"name": "iterative_c"},
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Return JSON only", messages[0]["content"])
        self.assertIn("hoge_streaming_intt_behavioral", messages[1]["content"])
        self.assertNotIn(LAB_ENDPOINT_ENV, messages[1]["content"])

    def test_build_chisel_generator_selection_messages(self):
        task = {
            "id": "yata_raintt_512_p27",
            "name": "YATA compressed RAINTT",
            "top_module": "YataRainttTop",
            "variant": "yata-raintt",
            "parameters": {"N": 512},
            "evaluation": {"mode": "verilator_test"},
        }
        messages = build_chisel_generator_selection_messages(
            task_file=Path("tasks/yata_raintt_512_p27.json"),
            task=task,
            search_point={"name": "iterative_c"},
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Return JSON only", messages[0]["content"])
        self.assertIn("chisel_reference", messages[1]["content"])
        self.assertNotIn(LAB_ENDPOINT_ENV, messages[1]["content"])

    def test_parse_behavioral_generator_selection(self):
        task = {
            "id": "hoge_streaming_intt_1024_p64",
            "top_module": "INTTWrap",
        }
        response = (
            "```json\n"
            '{"task_id":"hoge_streaming_intt_1024_p64",'
            '"generator":"hoge_streaming_intt_behavioral"}\n'
            "```"
        )

        selection = parse_behavioral_generator_selection(response, task)

        self.assertEqual(selection["task_id"], "hoge_streaming_intt_1024_p64")
        self.assertEqual(selection["generator"], "hoge_streaming_intt_behavioral")

    def test_parse_behavioral_generator_selection_rejects_wrong_generator(self):
        task = {
            "id": "hoge_streaming_intt_1024_p64",
            "top_module": "INTTWrap",
        }
        response = (
            '{"task_id":"hoge_streaming_intt_1024_p64",'
            '"generator":"hoge_nttid_behavioral"}'
        )

        with self.assertRaises(ValueError):
            parse_behavioral_generator_selection(response, task)

    def test_parse_chisel_generator_selection(self):
        task = {
            "id": "yata_raintt_512_p27",
            "top_module": "YataRainttTop",
        }
        response = (
            "```json\n"
            '{"task_id":"yata_raintt_512_p27",'
            '"generator":"chisel_reference"}\n'
            "```"
        )

        selection = parse_chisel_generator_selection(response, task)

        self.assertEqual(selection["task_id"], "yata_raintt_512_p27")
        self.assertEqual(selection["generator"], "chisel_reference")

    def test_parse_chisel_generator_selection_rejects_wrong_generator(self):
        task = {
            "id": "yata_raintt_512_p27",
            "top_module": "YataRainttTop",
        }
        response = '{"task_id":"yata_raintt_512_p27","generator":"behavioral"}'

        with self.assertRaises(ValueError):
            parse_chisel_generator_selection(response, task)

    def test_write_yata_behavioral_candidate(self):
        with TemporaryDirectory() as tmp:
            attempt_dir = Path(tmp)
            task = {
                "id": "yata_raintt_512_p27",
                "top_module": "YataRainttTop",
            }

            candidate = write_behavioral_candidate(
                task, attempt_dir, "YataRainttTop.v"
            )

            self.assertEqual(candidate, attempt_dir / "YataRainttTop.v")
            require_module(candidate.read_text(encoding="utf-8"), "YataRainttTop")

    def test_write_hoge_externalproduct_behavioral_candidate(self):
        with TemporaryDirectory() as tmp:
            attempt_dir = Path(tmp)
            task = {
                "id": "hoge_externalproduct_ntt_1024_p64",
                "top_module": "ExternalProductWrap",
            }

            candidate = write_behavioral_candidate(
                task, attempt_dir, "ExternalProductWrap.v"
            )

            self.assertEqual(candidate, attempt_dir / "ExternalProductWrap.v")
            require_module(
                candidate.read_text(encoding="utf-8"), "ExternalProductWrap"
            )

    def test_write_chisel_reference_candidate_uses_temp_build(self):
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            chisel_root = repo_root / "variants" / "example" / "chisel"
            (chisel_root / "project").mkdir(parents=True)
            (chisel_root / "src" / "main" / "scala").mkdir(parents=True)
            (chisel_root / "build.sbt").write_text("name := \"fake\"\n", encoding="utf-8")
            (chisel_root / "project" / "build.properties").write_text(
                "sbt.version=1.9.9\n",
                encoding="utf-8",
            )
            (chisel_root / "src" / "main" / "scala" / "Top.scala").write_text(
                "object Top\n",
                encoding="utf-8",
            )
            (chisel_root / "Top.v").write_text(
                "module Wrong(); endmodule\n",
                encoding="utf-8",
            )
            fake_sbt = repo_root / "fake-sbt"
            fake_sbt.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "test \"$1\" = run\n"
                "cat > Top.v <<'EOF'\n"
                "module Top(); endmodule\n"
                "EOF\n",
                encoding="utf-8",
            )
            fake_sbt.chmod(0o755)
            attempt_dir = repo_root / "build" / "attempt"
            attempt_dir.mkdir(parents=True)
            task = {
                "id": "fake_task",
                "variant": "example",
                "top_module": "Top",
            }

            candidate = write_chisel_reference_candidate(
                repo_root=repo_root,
                task=task,
                attempt_dir=attempt_dir,
                candidate_file="Top.v",
                sbt_bin=str(fake_sbt),
            )

            self.assertEqual(candidate, attempt_dir / "Top.v")
            self.assertEqual(
                candidate.read_text(encoding="utf-8"),
                "module Top(); endmodule\n",
            )
            self.assertIn(
                "returncode",
                (attempt_dir / "chisel_generate.json").read_text(encoding="utf-8"),
            )

    def test_write_chisel_reference_candidate_can_use_apptainer(self):
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            chisel_root = repo_root / "variants" / "example" / "chisel"
            (chisel_root / "project").mkdir(parents=True)
            (chisel_root / "src" / "main" / "scala").mkdir(parents=True)
            (chisel_root / "build.sbt").write_text("name := \"fake\"\n", encoding="utf-8")
            (chisel_root / "project" / "build.properties").write_text(
                "sbt.version=1.9.9\n",
                encoding="utf-8",
            )
            (chisel_root / "src" / "main" / "scala" / "Top.scala").write_text(
                "object Top\n",
                encoding="utf-8",
            )
            fake_apptainer = repo_root / "fake-apptainer"
            fake_apptainer.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "test \"$1\" = exec\n"
                "cat > Top.v <<'EOF'\n"
                "module Top(); endmodule\n"
                "EOF\n",
                encoding="utf-8",
            )
            fake_apptainer.chmod(0o755)
            sif = repo_root / "llm-ntt.sif"
            sif.write_text("fake image\n", encoding="utf-8")
            attempt_dir = repo_root / "build" / "attempt"
            attempt_dir.mkdir(parents=True)
            task = {
                "id": "fake_task",
                "variant": "example",
                "top_module": "Top",
            }

            candidate = write_chisel_reference_candidate(
                repo_root=repo_root,
                task=task,
                attempt_dir=attempt_dir,
                candidate_file="Top.v",
                sbt_bin="definitely-missing-sbt",
                apptainer_bin=str(fake_apptainer),
                sif=sif,
            )

            self.assertEqual(candidate.read_text(encoding="utf-8"), "module Top(); endmodule\n")
            metadata = (attempt_dir / "chisel_generate.json").read_text(encoding="utf-8")
            self.assertIn(str(fake_apptainer), metadata)
            self.assertIn(str(sif), metadata)

    def test_rejects_passthrough_for_arithmetic_task(self):
        task = {
            "id": "hoge_streaming_intt_1024_p64",
            "top_module": "INTTWrap",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 1024},
        }
        verilog = "module INTTWrap(input [1023:0] io_in, output [1023:0] io_out); assign io_out = io_in; endmodule\n"
        with self.assertRaises(ValueError):
            validate_candidate(verilog, task)

    def test_allows_passthrough_for_identity_task(self):
        task = {
            "id": "hoge_nttid_1024_identity",
            "top_module": "NTTidPackedTop",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 1024},
            "reference": {"operation": "identity modulo P"},
        }
        verilog = "module NTTidPackedTop(input [7:0] io_in, output [7:0] io_out); assign io_out = io_in; endmodule\n"
        validate_candidate(verilog, task)

    def test_rejects_placeholder_rtl(self):
        task = {
            "id": "hoge_streaming_intt_1024_p64",
            "top_module": "INTTWrap",
            "evaluation": {"mode": "verilator_test"},
            "parameters": {"N": 1024},
        }
        verilog = (
            "module INTTWrap(input clock, output io_validout);\n"
            "  // rest of the code omitted\n"
            "endmodule\n"
        )
        with self.assertRaises(ValueError):
            validate_candidate(verilog, task)


if __name__ == "__main__":
    unittest.main()
