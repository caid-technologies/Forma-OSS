from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from forma_core.persistence.project_artifacts import (
    ProjectArtifactStorage,
    ProjectArtifactStorageError,
    project_artifact_storage_key,
)
from forma_core.workspaces.projects.manifest import validate_artifact_references


class ProjectArtifactStorageTests(unittest.TestCase):
    def test_local_storage_round_trip_is_project_scoped(self) -> None:
        content = b"private project artifact"
        sha256 = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            storage = ProjectArtifactStorage(
                {
                    "enabled": True,
                    "backend": "local",
                    "directory": Path(directory),
                    "bucket": "unused",
                    "max_bytes": 1024,
                }
            )

            stored = storage.put("project-a", sha256, content, "application/octet-stream")
            restored = storage.get("project-a", sha256, "application/octet-stream")

            self.assertEqual(content, restored.content)
            self.assertTrue((Path(directory) / Path(*project_artifact_storage_key("project-a", sha256).split("/"))).is_file())
            with self.assertRaises(FileNotFoundError):
                storage.get("project-b", sha256, "application/octet-stream")
            self.assertEqual(sha256, stored.sha256)
            with self.assertRaisesRegex(ProjectArtifactStorageError, "does not match"):
                storage.put("project-a", "0" * 64, content, "application/octet-stream")
            self.assertEqual(1, storage.delete_project("project-a"))
            with self.assertRaises(FileNotFoundError):
                storage.get("project-a", sha256, "application/octet-stream")
            self.assertEqual(0, storage.delete_project("project-a"))

    def test_artifact_declarations_require_integrity_and_reject_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_artifact_references([{"path": "assembly.step", "media_type": "model/step"}])
        with self.assertRaisesRegex(ValueError, "escape"):
            validate_artifact_references(
                [{"path": "../secret.txt", "sha256": "0" * 64, "media_type": "text/plain"}]
            )
        with self.assertRaisesRegex(ValueError, "duplicated"):
            validate_artifact_references(
                [
                    {"path": "Assembly.step", "sha256": "0" * 64, "media_type": "model/step"},
                    {"path": "assembly.step", "sha256": "1" * 64, "media_type": "model/step"},
                ]
            )


if __name__ == "__main__":
    unittest.main()
