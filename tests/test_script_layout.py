from __future__ import annotations

from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
SCRIPT_CATEGORIES = {
    "continuous",
    "development",
    "media",
    "models",
    "operations",
    "quality",
}


class ScriptLayoutTests(unittest.TestCase):
    def test_script_root_is_an_index_not_a_flat_executable_directory(self) -> None:
        root_files = {path.name for path in SCRIPTS_DIR.iterdir() if path.is_file()}
        category_dirs = {
            path.name
            for path in SCRIPTS_DIR.iterdir()
            if path.is_dir() and path.name != "__pycache__"
        }

        self.assertEqual({"README.md", "__init__.py"}, root_files)
        self.assertEqual(SCRIPT_CATEGORIES, category_dirs)

    def test_python_script_groups_are_packages(self) -> None:
        for category in ("continuous", "media", "models", "operations"):
            self.assertTrue((SCRIPTS_DIR / category / "__init__.py").is_file())

    def test_script_index_describes_every_category(self) -> None:
        index = (SCRIPTS_DIR / "README.md").read_text(encoding="utf-8")

        for category in SCRIPT_CATEGORIES:
            self.assertIn(f"`{category}/`", index)


if __name__ == "__main__":
    unittest.main()
