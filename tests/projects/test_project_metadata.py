from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from forma_core import database


class ProjectMetadataUpdateTests(unittest.TestCase):
    def test_title_update_also_writes_hardware_ir_overview_title(self) -> None:
        project_id = "00000000-0000-0000-0000-000000000123"
        project = SimpleNamespace(
            hardware_ir={
                "overview": {"title": "Old lamp", "description": "Keep me"},
                "assembly_metadata": {"project_id": project_id},
            }
        )
        repository = Mock()
        repository.update_generated_project_metadata.return_value = True

        with (
            patch.object(database, "_DATABASE_REPOSITORY", repository),
            patch.object(database, "get_generated_project", return_value=project) as get_project,
            patch.object(database, "invalidate_project_lists"),
        ):
            updated = database.update_generated_project_metadata(
                project_id,
                owner_user_id="owner-1",
                title="Desk lamp",
            )

        self.assertTrue(updated)
        get_project.assert_called_once_with(project_id)
        updates = repository.update_generated_project_metadata.call_args.args[2]
        self.assertEqual("Desk lamp", updates["title"])
        self.assertEqual("Desk lamp", updates["hardware_ir"]["overview"]["title"])
        self.assertEqual("Keep me", updates["hardware_ir"]["overview"]["description"])
        self.assertEqual(project_id, updates["hardware_ir"]["assembly_metadata"]["project_id"])
        self.assertEqual("Old lamp", project.hardware_ir["overview"]["title"])

    def test_prompt_only_update_does_not_rewrite_hardware_ir(self) -> None:
        project_id = "00000000-0000-0000-0000-000000000124"
        repository = Mock()
        repository.update_generated_project_metadata.return_value = True

        with (
            patch.object(database, "_DATABASE_REPOSITORY", repository),
            patch.object(database, "get_generated_project") as get_project,
            patch.object(database, "invalidate_project_lists"),
        ):
            database.update_generated_project_metadata(
                project_id,
                owner_user_id="owner-1",
                prompt="Build a quieter fan.",
            )

        get_project.assert_not_called()
        updates = repository.update_generated_project_metadata.call_args.args[2]
        self.assertEqual({"prompt": "Build a quieter fan."}, updates)
