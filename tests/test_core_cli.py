from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from blueprint_core.cli.main import build_parser, main


class CoreCliTests(unittest.TestCase):
    def test_parser_describes_a_direct_core_cli(self) -> None:
        parser = build_parser()
        self.assertEqual("blueprint-core", parser.prog)
        self.assertIn("without a backend server", parser.description)

    def test_generate_supports_one_run_image_persistence_and_terminal_output(self) -> None:
        args = build_parser().parse_args([
            "generate",
            "make a sensor",
            "--generate-image",
            "--image-provider",
            "gmi",
            "--show-image",
        ])

        self.assertTrue(args.generate_image)
        self.assertEqual("gmi", args.image_provider)
        self.assertTrue(args.show_image)

    def test_workflows_lists_core_workflows_as_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["workflows", "--json"])

        self.assertEqual(0, exit_code)
        self.assertIn("default", [item["id"] for item in json.loads(stdout.getvalue())])

    def test_validate_reads_hardware_ir_without_a_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "project.json"
            project_path.write_text(json.dumps({"components": [], "nets": []}), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["validate", str(project_path)])

        self.assertEqual(0, exit_code)
        self.assertEqual({"critical": [], "info": [], "warning": []}, json.loads(stdout.getvalue())["validation"])

    def test_core_cli_is_a_package_not_another_flat_module(self) -> None:
        core_root = Path(__file__).resolve().parents[1] / "blueprint_core"
        self.assertTrue((core_root / "cli" / "main.py").exists())
        self.assertFalse((core_root / "cli.py").exists())


if __name__ == "__main__":
    unittest.main()
