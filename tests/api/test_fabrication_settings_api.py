"""Printer settings are owner-scoped data, never worker execution configuration."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from apps.api.auth import UserContext, require_user_context
from apps.api import readiness_api, user_settings_api
from forma_core import database
from forma_core.persistence.models import DBUserFabricationSettings
from forma_core.persistence.providers import create_sqlite_provider
from forma_core.persistence.repositories import SqlAlchemyRepository, SupabaseRepository
from forma_core.workspaces.projects.fabrication.models import PrinterConfigurationError


def user(owner="alice"):
    return UserContext(provider="test", subject=owner, owner_user_id=owner,
                       is_authenticated=bool(owner), is_admin=False)


@pytest.fixture()
def repository(tmp_path, monkeypatch):
    path = tmp_path / "settings.db"
    provider = create_sqlite_provider(source="test", url=f"sqlite:///{path}", import_legacy_jobs=False)
    provider.initialize()
    repo = SqlAlchemyRepository(provider.session_factory)
    monkeypatch.setattr(database, "_DATABASE_REPOSITORY", repo)
    yield repo, provider, path
    provider.dispose()


@pytest.fixture()
def client(repository):
    app = FastAPI()
    app.include_router(user_settings_api.router)
    app.include_router(readiness_api.router)
    app.dependency_overrides[require_user_context] = lambda: user()
    with TestClient(app) as test_client:
        yield test_client


def test_default_is_read_only_and_independent_of_slicer_installation(client, repository):
    with patch("forma_core.workspaces.projects.fabrication.slicers.orca.OrcaSlicerAdapter", side_effect=AssertionError("no slicer needed")):
        response = client.get("/user/settings/fabrication")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["source"] == "default"
    assert response.json()["printer_id"] == "creality_ender_3_04"
    assert len(response.json()["printers"]) == 2
    assert repository[0].get_user_fabrication_settings("alice") is None


def test_settings_roundtrip_isolated_per_owner_and_survives_database_reopen(client, repository, monkeypatch):
    response = client.put("/user/settings/fabrication", json={"printer_id": "bambu_a1_04"})
    assert response.status_code == 200
    assert response.json()["source"] == "user"
    assert response.json()["updated_at"]
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get("/user/settings/fabrication").json()["printer_id"] == "bambu_a1_04"
    client.app.dependency_overrides[require_user_context] = lambda: user("bob")
    assert client.get("/user/settings/fabrication").json()["source"] == "default"
    assert client.put("/user/settings/fabrication", json={"printer_id": "creality_ender_3_04"}).status_code == 200
    _, _, db_path = repository
    reopened = create_sqlite_provider(source="reopened", url=f"sqlite:///{db_path}", import_legacy_jobs=False)
    try:
        reopened.initialize()
        monkeypatch.setattr(database, "_DATABASE_REPOSITORY", SqlAlchemyRepository(reopened.session_factory))
        assert database.get_user_fabrication_settings("alice")["printer_id"] == "bambu_a1_04"
        assert database.get_user_fabrication_settings("bob")["printer_id"] == "creality_ender_3_04"
    finally:
        reopened.dispose()


def test_repeated_saves_update_one_row_without_resetting_privacy(repository):
    database.set_user_model_training_preference("alice", allow_model_training=False, updated_at="before")
    for value in ["bambu_a1_04", "creality_ender_3_04", "bambu_a1_04"]:
        database.set_user_fabrication_settings("alice", printer_id=value, updated_at="after")
    assert database.get_user_settings("alice").model_training_opt_out is True
    database.set_user_model_training_preference("alice", allow_model_training=True, updated_at="later")
    assert database.get_user_fabrication_settings("alice")["printer_id"] == "bambu_a1_04"
    with repository[1].session_factory() as session:
        assert session.query(DBUserFabricationSettings).count() == 1


@pytest.mark.parametrize("payload", [
    {}, {"printer_id": None}, {"printer_id": "unknown"}, {"printer_id": "../../bin/sh"},
    {"printer_id": "bambu_a1_04", "owner_user_id": "bob"},
    {"printer_id": "bambu_a1_04", "orca_path": "/bin/sh"},
    {"printer_id": "bambu_a1_04", "native_settings": ["/secret"]},
    {"printer_id": "bambu_a1_04", "start_gcode": "M104 S999"},
    {"printer_id": "bambu_a1_04", "nozzle_mm": 0.8},
])
def test_unreviewed_settings_and_owner_spoofing_rejected(client, repository, payload):
    assert client.put("/user/settings/fabrication", json=payload).status_code == 422
    assert repository[0].get_user_fabrication_settings("alice") is None
    assert repository[0].get_user_fabrication_settings("bob") is None


def test_missing_identity_cannot_read_or_write(client):
    client.app.dependency_overrides[require_user_context] = lambda: user(None)
    assert client.get("/user/settings/fabrication").status_code == 401
    assert client.put("/user/settings/fabrication", json={"printer_id": "bambu_a1_04"}).status_code == 401


def test_both_routes_use_auth_dependency():
    routes = [r for r in user_settings_api.router.routes if isinstance(r, APIRoute) and r.path.endswith("/fabrication")]
    assert len(routes) == 2
    assert all(require_user_context in {d.call for d in r.dependant.dependencies} for r in routes)


@pytest.mark.parametrize("method", ["get", "put"])
def test_database_errors_are_not_silent_success_or_server_detail_leaks(client, repository, monkeypatch, method):
    name = "get_user_fabrication_settings" if method == "get" else "upsert_user_fabrication_settings"
    monkeypatch.setattr(repository[0], name, Mock(side_effect=RuntimeError("secret-db-host password=private")))
    response = (client.get("/user/settings/fabrication") if method == "get"
                else client.put("/user/settings/fabrication", json={"printer_id": "bambu_a1_04"}))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "fabrication_settings_unavailable"
    assert "secret-db-host" not in response.text


def test_supabase_contract_scopes_reads_and_upserts_by_authenticated_owner():
    client = Mock()
    query = client.table.return_value
    query.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    repository = SupabaseRepository(client)
    assert repository.get_user_fabrication_settings("alice") is None
    client.table.assert_called_with("user_fabrication_settings")
    query.select.return_value.eq.assert_called_once_with("owner_user_id", "alice")
    record = {"owner_user_id": "alice", "printer_id": "bambu_a1_04", "updated_at": "now"}
    query.upsert.return_value.execute.return_value.data = [record]
    assert repository.upsert_user_fabrication_settings(record).printer_id == "bambu_a1_04"
    query.upsert.assert_called_once_with(record, on_conflict="owner_user_id")
    query.upsert.return_value.execute.return_value.data = []
    with pytest.raises(RuntimeError, match="no persisted record"):
        repository.upsert_user_fabrication_settings(record)


def test_supabase_migration_is_server_owned():
    sql = (Path(__file__).parents[2] / "supabase/migrations/20260915211000_user_fabrication_settings.sql").read_text()
    assert "enable row level security" in sql
    assert "revoke all on table public.user_fabrication_settings from public, anon, authenticated" in sql
    assert "grant select, insert, update, delete on table public.user_fabrication_settings to service_role" in sql


@pytest.mark.parametrize("owner", ["", " ", None])
def test_database_boundary_requires_owner(repository, owner):
    with pytest.raises(ValueError, match="owner_user_id"):
        database.get_user_fabrication_settings(owner)
    with pytest.raises(ValueError, match="owner_user_id"):
        database.set_user_fabrication_settings(owner, printer_id="bambu_a1_04", updated_at="now")


@pytest.mark.parametrize("explicit, expected", [(None, "bambu_a1_04"), ("creality_ender_3_04", "creality_ender_3_04")])
def test_gcode_request_uses_saved_preference_unless_explicitly_overridden(client, explicit, expected):
    client.put("/user/settings/fabrication", json={"printer_id": "bambu_a1_04"})
    # Stop at the slicer availability boundary; no fake G-code is claimed as native output.
    with patch.object(readiness_api, "_project_cad", return_value={}), patch.object(
        readiness_api, "_load_step_bytes", return_value=("a" * 64, b"STEP")
    ), patch.object(readiness_api, "resolve_demo_slice_profile", side_effect=PrinterConfigurationError("private worker path")) as resolve:
        response = client.post(f"/projects/{uuid4()}/exports/gcode", json={"printer_id": explicit} if explicit else {})
    resolve.assert_called_once_with(expected)
    assert response.status_code == 503
    assert "private worker path" not in response.text
    assert client.get("/user/settings/fabrication").json()["printer_id"] == "bambu_a1_04"


def test_manifest_includes_account_preference_not_first_available_printer(client):
    client.put("/user/settings/fabrication", json={"printer_id": "bambu_a1_04"})
    with patch.object(readiness_api, "_project_cad", return_value={"sha256": "a" * 64}), patch.object(
        readiness_api, "demo_printer_capabilities", return_value=[]
    ):
        response = client.get(f"/projects/{uuid4()}/exports")
    assert response.status_code == 200
    assert response.json()["preferred_printer_id"] == "bambu_a1_04"


def test_cross_owner_project_access_fails_before_preferences_or_slicer(client):
    with patch.object(readiness_api, "get_project_identity", return_value={"owner_user_id": "bob"}), patch.object(
        readiness_api, "get_user_fabrication_settings"
    ) as preference:
        response = client.post(f"/projects/{uuid4()}/exports/gcode", json={})
    assert response.status_code == 404
    preference.assert_not_called()


def test_invalid_printer_override_is_validation_error(client):
    assert client.post(f"/projects/{uuid4()}/exports/gcode", json={"printer_id": "unknown"}).status_code == 422


def test_settings_database_outage_does_not_hide_step_manifest(client, repository, monkeypatch):
    monkeypatch.setattr(repository[0], "get_user_fabrication_settings", Mock(side_effect=RuntimeError("db unavailable")))
    with patch.object(readiness_api, "_project_cad", return_value={"sha256": "a" * 64}), patch.object(
        readiness_api, "demo_printer_capabilities", return_value=[]
    ):
        response = client.get(f"/projects/{uuid4()}/exports")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["step"]["sha256"] == "a" * 64
    assert response.json()["preferred_printer_id"] is None
    assert response.json()["preference_error"] == "fabrication_settings_unavailable"
