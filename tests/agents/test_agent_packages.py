from __future__ import annotations

import ast
from pathlib import Path
import unittest

import blueprint_core.agents as agents
from blueprint_core.agents.clarification import ContextClarifierAgent
from blueprint_core.agents.context_gathering import ContextGatheringAgent
from blueprint_core.agents.continuous import ContinuousAgentCoordinator
from blueprint_core.agents.project_correction import ProjectSelfCorrectionAgent
from blueprint_core.agents.prompt_compaction import PromptCompactionAgent
from blueprint_core.agents.video_correction import FireworksVideoSelfCorrectionAgent


class AgentPackageTests(unittest.TestCase):
    def test_common_agents_are_discoverable_from_the_package(self) -> None:
        self.assertIs(agents.ContextClarifierAgent, ContextClarifierAgent)
        self.assertIs(agents.ContextGatheringAgent, ContextGatheringAgent)
        self.assertIs(agents.ContinuousAgentCoordinator, ContinuousAgentCoordinator)
        self.assertIs(agents.ProjectSelfCorrectionAgent, ProjectSelfCorrectionAgent)
        self.assertIs(agents.PromptCompactionAgent, PromptCompactionAgent)
        self.assertIs(agents.FireworksVideoSelfCorrectionAgent, FireworksVideoSelfCorrectionAgent)

    def test_agent_classes_are_defined_only_in_the_agents_package(self) -> None:
        package_root = Path(__file__).resolve().parents[2] / "blueprint_core"
        misplaced: list[str] = []
        for path in package_root.rglob("*.py"):
            relative_path = path.relative_to(package_root)
            if relative_path.parts[0] == "agents":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and "Agent" in node.name:
                    misplaced.append(f"{relative_path}:{node.lineno}:{node.name}")

        self.assertEqual([], misplaced)

    def test_legacy_agent_modules_are_removed(self) -> None:
        package_root = Path(__file__).resolve().parents[2] / "blueprint_core"
        legacy_modules = (
            "clarifying_questions.py",
            "continuous_agents.py",
            "continuous_openai_jobs.py",
            "lattice.py",
            "lattice_agents.py",
            "pipeline.py",
            "prompt_compaction.py",
        )
        self.assertEqual([], [name for name in legacy_modules if (package_root / name).exists()])


if __name__ == "__main__":
    unittest.main()
