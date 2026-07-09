from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blueprint_core.terminal_images import TerminalImageRenderConfig, TerminalImageRenderer, extract_image_paths, is_image_path


class TerminalImageTests(unittest.TestCase):
    def test_renderer_outputs_ansi_blocks_for_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blue.png"

            from PIL import Image

            Image.new("RGB", (8, 8), color=(0, 80, 255)).save(path)

            renderer = TerminalImageRenderer(TerminalImageRenderConfig(width=8, max_height=4))
            rendered = renderer.render(path)

            self.assertIn("\033[38;2;", rendered)
            self.assertIn("\033[48;2;", rendered)

    def test_extract_image_paths_finds_local_image_strings(self) -> None:
        payload = {
            "image_reports": [
                {"path": "outputs/render.png"},
                {"path": "https://example.com/remote.png"},
            ],
            "nested": {"preview": "see artifact.webp now"},
        }

        paths = extract_image_paths(payload, base_dir=Path("/tmp/project"))

        self.assertEqual(
            [Path("/tmp/project/outputs/render.png"), Path("/tmp/project/artifact.webp")],
            list(paths),
        )
        self.assertTrue(is_image_path("render.jpeg"))
        self.assertFalse(is_image_path("https://example.com/render.jpeg"))


if __name__ == "__main__":
    unittest.main()
