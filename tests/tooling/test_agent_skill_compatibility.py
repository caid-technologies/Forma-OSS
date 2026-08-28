from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID


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

    def test_project_allocator_uses_a_generated_uuid_under_the_workspace(self) -> None:
        script = SKILL_ROOT / "scripts" / "create_project.py"
        spec = importlib.util.spec_from_file_location("forma_skill_project", script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "forma-workspace"
            project_path = module.create_project_directory(workspace)
            self.assertEqual(workspace, project_path.parent)
            UUID(project_path.name)
            self.assertTrue(project_path.is_dir())

    def test_cad_adapter_declares_managed_native_dependency(self) -> None:
        script = SKILL_ROOT / "scripts" / "cad.py"
        content = script.read_text(encoding="utf-8")
        self.assertIn('SUPPORTED_OPENCAD_VERSION = "0.2.3"', content)
        self.assertIn('DEFAULT_OPENCAD_REQUIREMENT = f"opencad[occt]=={SUPPORTED_OPENCAD_VERSION}"', content)
        self.assertIn('create_backend("occt", require_native=True)', content)
        self.assertIn("FORMA_OPENCAD_REQUIREMENT", content)

    def test_base_core_dependencies_do_not_include_opencad(self) -> None:
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("opencad", pyproject.lower())
        self.assertNotIn("opencad", requirements.lower())


if __name__ == "__main__":
    unittest.main()
