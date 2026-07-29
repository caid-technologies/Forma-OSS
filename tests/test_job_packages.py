from __future__ import annotations

import ast
from pathlib import Path
import unittest

from blueprint_core.jobs.continuous import ContinuousOpenAIJobRunner
from blueprint_core.jobs.persistence import DBA2AJob
from blueprint_core.jobs.schema import JOB_TABLE_CONTRACT
from blueprint_core.jobs.store import JobMetadataStore
from blueprint_core.persistence.models import Base
from blueprint_core.persistence.schema import APPLICATION_SCHEMA


class JobPackageTests(unittest.TestCase):
    def test_job_implementations_use_the_jobs_package(self) -> None:
        self.assertEqual("blueprint_core.jobs.continuous", ContinuousOpenAIJobRunner.__module__)
        self.assertEqual("blueprint_core.jobs.store", JobMetadataStore.__module__)
        self.assertEqual("blueprint_core.jobs.persistence", DBA2AJob.__module__)

    def test_job_persistence_model_and_schema_contract_are_registered(self) -> None:
        self.assertIn("a2a_jobs", Base.metadata.tables)
        self.assertIn(JOB_TABLE_CONTRACT, APPLICATION_SCHEMA)

    def test_job_classes_are_defined_only_in_the_jobs_package(self) -> None:
        package_root = Path(__file__).resolve().parents[1] / "blueprint_core"
        misplaced: list[str] = []
        for path in package_root.rglob("*.py"):
            relative_path = path.relative_to(package_root)
            if relative_path.parts[0] == "jobs":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and "Job" in node.name:
                    misplaced.append(f"{relative_path}:{node.lineno}:{node.name}")

        self.assertEqual([], misplaced)

    def test_legacy_job_modules_are_removed(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        legacy_paths = (
            "apps/api/job_source_usage.py",
            "apps/api/job_store.py",
            "blueprint_core/agents/continuous_jobs.py",
            "blueprint_core/job_source_usage.py",
            "blueprint_core/persistence/repositories/jobs.py",
        )
        self.assertEqual([], [path for path in legacy_paths if (repository_root / path).exists()])


if __name__ == "__main__":
    unittest.main()
