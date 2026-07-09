from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest
import json


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run-terminal-dashboard.py"
VIDEO_SCRIPT_PATH = ROOT_DIR / "scripts" / "render-mech-video.py"


def load_dashboard_module():
    spec = importlib.util.spec_from_file_location("run_terminal_dashboard", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run-terminal-dashboard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_video_module():
    spec = importlib.util.spec_from_file_location("render_mech_video", VIDEO_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load render-mech-video.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TerminalDashboardScriptTests(unittest.TestCase):
    def test_generate_request_payload(self) -> None:
        module = load_dashboard_module()

        request = module.GenerateRequest(
            prompt="blue monitor",
            workflow="default",
            provider="baseten",
            model="zai-org/GLM-5.2",
            generate_image=True,
        )

        self.assertEqual(
            {
                "prompt": "blue monitor",
                "workflow": "default",
                "provider": "baseten",
                "model": "zai-org/GLM-5.2",
                "generate_image": True,
                "image_data": None,
            },
            request.to_json_obj(),
        )

    def test_url_helpers(self) -> None:
        module = load_dashboard_module()

        self.assertEqual("http://127.0.0.1:8000/api", module.normalize_backend_url("http://127.0.0.1:8000"))
        self.assertEqual("http://127.0.0.1:8000/api", module.normalize_backend_url("http://127.0.0.1:8000/api/"))
        self.assertEqual("http://127.0.0.1:3000/project/proj%201?tab=mechanical", module.build_project_snapshot_target("http://127.0.0.1:3000", "proj 1", tab="mechanical").url)
        self.assertEqual("http://127.0.0.1:3000/?example=plant_watering&tab=mechanical", module.build_example_snapshot_target("http://127.0.0.1:3000", "plant_watering.json", tab="mechanical").url)

    def test_find_chromium_accepts_explicit_path(self) -> None:
        module = load_dashboard_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            executable = pathlib.Path(temp_dir) / "chromium"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")

            self.assertEqual(str(executable), module.find_chromium(str(executable)))

    def test_pillow_dashboard_renderer_writes_png(self) -> None:
        from blueprint_core.terminal_dashboard import DashboardRenderConfig, render_dashboard_image

        project_ir = json.loads((ROOT_DIR / "frontend" / "public" / "examples" / "plant_watering.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = pathlib.Path(temp_dir) / "dashboard.png"

            render_dashboard_image(project_ir, output_path, config=DashboardRenderConfig(width=720, height=520))

            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 1000)

    def test_backend_failure_excerpt_prefers_error_lines(self) -> None:
        module = load_dashboard_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = pathlib.Path(temp_dir) / "backend.log"
            log_path.write_text(
                "\n".join(
                    [
                        "INFO startup",
                        "2026 ERROR LLM structured call failed via baseten: Invalid JSON",
                        "INFO shutdown",
                    ]
                ),
                encoding="utf-8",
            )

            excerpt = module.backend_failure_excerpt(log_path, start_offset=0)

        self.assertIn("LLM structured call failed", excerpt)
        self.assertIn("Invalid JSON", excerpt)
        self.assertNotIn("INFO startup", excerpt)

    def test_video_helpers_unwrap_generated_response(self) -> None:
        module = load_video_module()

        self.assertEqual(18, module.frame_count(1.0, 18))
        self.assertEqual({"overview": {"title": "x"}}, module.project_ir_from_payload({"project_ir": {"overview": {"title": "x"}}}))


if __name__ == "__main__":
    unittest.main()
