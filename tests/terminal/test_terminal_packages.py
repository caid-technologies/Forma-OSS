from __future__ import annotations

from pathlib import Path
import unittest

from forma_core.terminal.dashboard import DashboardRenderConfig, render_dashboard_image
from forma_core.terminal.images import TerminalImageRenderConfig, TerminalImageRenderer


class TerminalPackageTests(unittest.TestCase):
    def test_terminal_implementations_use_the_terminal_package(self) -> None:
        self.assertEqual("forma_core.terminal.dashboard", DashboardRenderConfig.__module__)
        self.assertEqual("forma_core.terminal.dashboard", render_dashboard_image.__module__)
        self.assertEqual("forma_core.terminal.images", TerminalImageRenderConfig.__module__)
        self.assertEqual("forma_core.terminal.images", TerminalImageRenderer.__module__)

    def test_legacy_terminal_modules_are_removed(self) -> None:
        package_root = Path(__file__).resolve().parents[2] / "forma_core"
        legacy_modules = ("terminal_dashboard.py", "terminal_images.py")
        self.assertEqual([], [name for name in legacy_modules if (package_root / name).exists()])


if __name__ == "__main__":
    unittest.main()
