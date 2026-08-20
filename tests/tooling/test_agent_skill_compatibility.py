from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "forma-hardware"


class AgentSkillCompatibilityTests(unittest.TestCase):
    def test_shared_agent_skill_has_portable_frontmatter(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertTrue(content.startswith("---\nname: forma-hardware\n"))
        self.assertIn("\ndescription:", content.split("---", 2)[1])
        self.assertIn("OpenClaw", content)
        self.assertIn("NemoClaw", content)
        self.assertIn("OpenCode", content)

    def test_bundled_client_accepts_options_after_subcommand(self) -> None:
        script = SKILL_ROOT / "scripts" / "forma.py"
        spec = importlib.util.spec_from_file_location("forma_skill_client", script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        args = module.build_parser().parse_args(
            [
                "compile",
                "project.json",
                "--authoring-agent",
                "nemoclaw",
                "--output",
                "compiled.json",
            ]
        )

        self.assertEqual("nemoclaw", args.authoring_agent)
        self.assertEqual("compiled.json", args.output)


if __name__ == "__main__":
    unittest.main()
