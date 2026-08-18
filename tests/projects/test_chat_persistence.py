from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueprint_core import database
from blueprint_core.workspaces.projects import ProjectStateError


class ChatProjectValidationTests(unittest.TestCase):
    def _upsert(self) -> None:
        database.upsert_project_chat(
            chat_id="chat-1",
            owner_user_id="owner-1",
            title="Canonical project chat",
            messages=[
                {
                    "id": "message-1",
                    "role": "assistant",
                    "content": "Your project is ready.",
                    "projectId": "00000000-0000-0000-0000-000000000001",
                }
            ],
            created_at="2026-08-06T12:00:00Z",
            updated_at="2026-08-06T12:00:01Z",
        )

    def test_chat_accepts_project_from_canonical_revision_store(self) -> None:
        repository = Mock()
        repository.upsert_project_chat.return_value = SimpleNamespace(chat_id="chat-1")

        with (
            patch.object(database, "_DATABASE_REPOSITORY", repository),
            patch.object(database, "get_generated_project", return_value=None),
            patch.object(
                database,
                "get_latest_project_revision",
                return_value=SimpleNamespace(revision=1),
            ) as get_revision,
        ):
            self._upsert()

        get_revision.assert_called_once_with(
            "00000000-0000-0000-0000-000000000001",
            "owner-1",
        )
        repository.upsert_project_chat.assert_called_once()

    def test_chat_rejects_canonical_project_not_owned_by_chat_owner(self) -> None:
        repository = Mock()

        with (
            patch.object(database, "_DATABASE_REPOSITORY", repository),
            patch.object(database, "get_generated_project", return_value=None),
            patch.object(
                database,
                "get_latest_project_revision",
                side_effect=ProjectStateError(
                    "project_revision_not_found",
                    "Project revision not found.",
                ),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "deleted or missing project"):
                self._upsert()

        repository.upsert_project_chat.assert_not_called()

    def test_chat_still_rejects_deleted_legacy_project(self) -> None:
        repository = Mock()

        with (
            patch.object(database, "_DATABASE_REPOSITORY", repository),
            patch.object(
                database,
                "get_generated_project",
                return_value=SimpleNamespace(status="deletion_pending"),
            ),
            patch.object(database, "get_latest_project_revision") as get_revision,
        ):
            with self.assertRaisesRegex(ValueError, "deleted or missing project"):
                self._upsert()

        get_revision.assert_not_called()
        repository.upsert_project_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
