"""Tests for per-user project ownership (owner_id column + access helpers)."""

from __future__ import annotations

import os
import unittest
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator, Optional
from unittest import mock

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import current_owner_id, ensure_project_access
from blueprint_core import database

# Every env var that influences auth behavior, defaulted to "disabled" so tests
# are hermetic regardless of the developer's shell/.env state.
BASE_ENV = {
    "BLUEPRINT_DEPLOYMENT": "",
    "BLUEPRINT_DEPLOYMENT_MODE": "",
    "DEPLOYMENT": "",
    "DEPLOYMENT_MODE": "",
    "NEXT_PUBLIC_BLUEPRINT_DEPLOYMENT": "",
    "BLUEPRINT_DISABLE_AUTH": "",
}


def env(**overrides):
    return mock.patch.dict(os.environ, {**BASE_ENV, **overrides})


def auth_on_env():
    return env(BLUEPRINT_DEPLOYMENT="true")


def fake_request(sub: Optional[str] = None):
    claims = {"sub": sub} if sub else {}
    return SimpleNamespace(scope={"state": {"clerk_claims": claims}})


@contextmanager
def sqlite_backend() -> Iterator[None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with mock.patch.object(database, "DATABASE_BACKEND", "sqlite"), \
            mock.patch.object(database, "engine", engine), \
            mock.patch.object(database, "SessionLocal", session_factory):
        yield
    engine.dispose()


def save_project(owner_id: Optional[str] = None) -> str:
    project_id = str(uuid.uuid4())
    database.save_generated_project(
        project_id=project_id,
        title="LED Controller",
        prompt="Blink an LED",
        hardware_ir={"assembly_metadata": {}},
        created_at="2026-07-14T00:00:00Z",
        owner_id=owner_id,
    )
    return project_id


class OwnershipPersistenceTests(unittest.TestCase):
    def test_save_persists_owner_id_and_defaults_to_null(self) -> None:
        with sqlite_backend():
            owned_id = save_project(owner_id="user_a")
            legacy_id = save_project()

            owned = database.get_generated_project(owned_id)
            legacy = database.get_generated_project(legacy_id)

        self.assertEqual(owned.owner_id, "user_a")
        self.assertIsNone(legacy.owner_id)

    def test_owner_filtered_list_excludes_other_and_legacy_rows(self) -> None:
        with sqlite_backend():
            first_a = save_project(owner_id="user_a")
            save_project(owner_id="user_b")
            save_project()  # legacy NULL owner
            second_a = save_project(owner_id="user_a")

            projects = database.list_generated_projects(owner_id="user_a")

        self.assertEqual([p.project_id for p in projects], [second_a, first_a])

    def test_unfiltered_list_returns_everything(self) -> None:
        with sqlite_backend():
            save_project(owner_id="user_a")
            save_project(owner_id="user_b")
            save_project()

            projects = database.list_generated_projects()

        self.assertEqual(len(projects), 3)

    def test_delete_removes_row_and_is_idempotent(self) -> None:
        with sqlite_backend():
            project_id = save_project(owner_id="user_a")

            self.assertTrue(database.delete_generated_project(project_id))
            self.assertIsNone(database.get_generated_project(project_id))
            self.assertFalse(database.delete_generated_project(project_id))

    def test_delete_with_owner_filter_only_removes_matching_owner(self) -> None:
        with sqlite_backend():
            project_id = save_project(owner_id="user_a")

            self.assertFalse(database.delete_generated_project(project_id, owner_id="user_b"))
            self.assertIsNotNone(database.get_generated_project(project_id))
            self.assertTrue(database.delete_generated_project(project_id, owner_id="user_a"))
            self.assertIsNone(database.get_generated_project(project_id))


class CurrentOwnerIdTests(unittest.TestCase):
    def test_returns_sub_from_verified_claims(self) -> None:
        self.assertEqual(current_owner_id(fake_request("user_123")), "user_123")

    def test_returns_none_without_claims(self) -> None:
        self.assertIsNone(current_owner_id(fake_request()))
        self.assertIsNone(current_owner_id(SimpleNamespace(scope={})))
        self.assertIsNone(current_owner_id(SimpleNamespace(scope={"state": {}})))


class EnsureProjectAccessTests(unittest.TestCase):
    def test_auth_off_never_raises(self) -> None:
        project = SimpleNamespace(owner_id="someone_else")
        with env():
            ensure_project_access(project, fake_request())
            ensure_project_access(project, fake_request("user_a"))

    def test_owner_passes_when_auth_on(self) -> None:
        project = SimpleNamespace(owner_id="user_a")
        with auth_on_env():
            ensure_project_access(project, fake_request("user_a"))

    def test_foreign_project_raises_404(self) -> None:
        project = SimpleNamespace(owner_id="user_a")
        with auth_on_env():
            with self.assertRaises(HTTPException) as ctx:
                ensure_project_access(project, fake_request("user_b"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_legacy_null_owner_hidden_when_auth_on(self) -> None:
        project = SimpleNamespace(owner_id=None)
        with auth_on_env():
            with self.assertRaises(HTTPException) as ctx:
                ensure_project_access(project, fake_request("user_a"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_missing_sub_raises_404(self) -> None:
        project = SimpleNamespace(owner_id="user_a")
        with auth_on_env():
            with self.assertRaises(HTTPException) as ctx:
                ensure_project_access(project, fake_request())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_row_without_owner_attribute_fails_closed(self) -> None:
        project = SimpleNamespace()  # e.g. Supabase row missing the column
        with auth_on_env():
            with self.assertRaises(HTTPException) as ctx:
                ensure_project_access(project, fake_request("user_a"))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
