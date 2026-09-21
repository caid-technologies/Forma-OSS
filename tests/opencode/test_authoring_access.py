from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from apps.api import main, opencode_api
from apps.api.auth import UserContext, has_opencode_authoring_access
from apps.api.hosted_chat import require_hosted_chat_enabled
from forma_core.opencode.store import OpenCodeStore


def user_context(provider="clerk", *, authenticated=True, owner="new-user", admin=False):
    return UserContext(
        provider=provider,
        subject=owner,
        owner_user_id=owner,
        is_authenticated=authenticated,
        is_admin=admin,
    )


@pytest.mark.parametrize("provider", ["clerk", "forma-cli"])
@pytest.mark.parametrize("legacy_allowlist", ["", "pilot@example.com"])
def test_every_signed_in_user_has_access_without_an_email_lookup(provider, legacy_allowlist):
    with patch.dict(os.environ, {"FORMA_OPENCODE_ALLOWED_EMAILS": legacy_allowlist}, clear=True), patch(
        "apps.api.auth.clerk_user_email", side_effect=AssertionError("No profile lookup needed")
    ):
        user = user_context(provider)
        assert has_opencode_authoring_access(user)
        with patch.dict(os.environ, {"FORMA_DEPLOYMENT_MODE": "hosted", "FORMA_HOSTED_CHAT_ENABLED": "false"}):
            require_hosted_chat_enabled(user)


@pytest.mark.parametrize("user", [
    None,
    user_context(authenticated=False),
    user_context(owner=None),
    user_context("mcp-api-key", admin=True),
    user_context("a2a-api-key"),
    user_context("unknown", admin=True),
])
def test_authoring_access_requires_an_authenticated_user_identity(user):
    assert not has_opencode_authoring_access(user)


def test_local_authoring_still_requires_explicit_opt_in():
    with patch.dict(os.environ, {}, clear=True):
        assert not has_opencode_authoring_access(user_context("local"))
        with patch.dict(os.environ, {"FORMA_OPENCODE_ALLOW_LOCAL": "true"}):
            assert has_opencode_authoring_access(user_context("local"))
            assert not has_opencode_authoring_access(user_context("local", authenticated=False))


@pytest.fixture
def authoring_client():
    app = FastAPI()
    app.include_router(opencode_api.router)
    app.add_api_route("/runtime/config", main.runtime_config_endpoint)
    app.add_api_route("/chats/{chat_id}", main.upsert_chat_endpoint, methods=["PUT"])
    store = OpenCodeStore(":memory:")
    environment = {
        "FORMA_DEPLOYMENT_MODE": "hosted",
        "FORMA_AUTH_MODE": "clerk",
        "FORMA_AUTHORING_MODE_ENABLED": "true",
        "FORMA_HOSTED_CHAT_ENABLED": "false",
        "FORMA_OPENCODE_ALLOWED_EMAILS": "pilot@example.com",
        "FORMA_USER_SECRETS_KEY": "test-authoring-secret-key",
    }
    try:
        with patch.dict(os.environ, environment, clear=True), patch.object(
            opencode_api, "OPENCODE_STORE", store
        ), patch("apps.api.auth.resolve_access_token", return_value=None), patch(
            "apps.api.auth.verify_clerk_bearer_token",
            side_effect=lambda token: {"sub": token},
        ), patch("apps.api.auth.clerk_user_email", side_effect=AssertionError("No profile lookup needed")), TestClient(app) as client:
            yield client, store
    finally:
        store.close()


def test_signed_in_non_admin_can_create_a_project_session_and_queue_generation(authoring_client):
    client, store = authoring_client
    headers = {"Authorization": "Bearer new-user"}
    created = client.post("/opencode/sessions", json={"connector_id": "mini-pc-1"}, headers=headers)
    assert created.status_code == 201, created.text
    session = created.json()
    assert store.get_session(session["session_id"]).owner_user_id == "new-user"
    queued = client.post(
        f"/opencode/sessions/{session['session_id']}/commands",
        json={"message": "Build a mechanical bracket", "idempotency_key": "first-project"},
        headers=headers,
    )
    assert queued.status_code == 201, queued.text
    assert queued.json()["status"] == "queued"
    command = store.claim_next(connector_id="mini-pc-1", session_id=session["session_id"])
    assert command.message == "Build a mechanical bracket"


def test_authoring_user_can_save_chat_while_legacy_hosted_generation_is_disabled(authoring_client):
    client, _ = authoring_client
    message = {"id": "original", "role": "user", "content": "Keep the gear mechanical"}
    with patch("apps.api.main.upsert_project_chat", side_effect=lambda **record: SimpleNamespace(**record)) as save:
        response = client.put("/chats/gear-chat", headers={"Authorization": "Bearer new-user"},
                              json={"title": "Gear", "messages": [message]})
        assert response.status_code == 200, response.text
        assert response.json()["messages"][0]["content"] == message["content"]
        assert save.call_args.kwargs["owner_user_id"] == "new-user"
        save.reset_mock()
        assert client.put("/chats/gear-chat", json={"title": "Gear", "messages": [message]}).status_code == 401
        save.assert_not_called()


def test_signed_out_requests_cannot_create_or_submit_generation(authoring_client):
    client, store = authoring_client
    with patch.object(store, "create_session") as create, patch.object(store, "create_command") as submit:
        assert client.post("/opencode/sessions", json={"connector_id": "mini-pc-1"}).status_code == 401
        assert client.post(
            "/opencode/sessions/unknown/commands",
            json={"message": "Build a bracket", "idempotency_key": "anonymous"},
        ).status_code == 401
        create.assert_not_called()
        submit.assert_not_called()


def test_invalid_session_token_cannot_start_generation(authoring_client):
    client, store = authoring_client
    with patch("apps.api.auth.verify_clerk_bearer_token", side_effect=HTTPException(status_code=401)), patch.object(
        store, "create_session"
    ) as create:
        assert client.post(
            "/opencode/sessions", json={"connector_id": "mini-pc-1"},
            headers={"Authorization": "Bearer invalid-token"},
        ).status_code == 401
        create.assert_not_called()


@pytest.mark.parametrize("provider", ["mcp-api-key", "a2a-api-key"])
def test_service_identity_cannot_start_user_generation(authoring_client, provider):
    client, store = authoring_client
    with patch("apps.api.auth.require_user_context", new=AsyncMock(return_value=user_context(provider, admin=True))), patch.object(
        store, "create_session"
    ) as create:
        response = client.post("/opencode/sessions", json={"connector_id": "mini-pc-1"})
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "opencode_user_required"
        create.assert_not_called()


def test_signed_in_users_cannot_access_another_users_session_or_project(authoring_client):
    client, _ = authoring_client
    session = client.post(
        "/opencode/sessions", json={"connector_id": "mini-pc-1"},
        headers={"Authorization": "Bearer owner"},
    ).json()
    headers = {"Authorization": "Bearer other-user"}
    path = f"/opencode/sessions/{session['session_id']}"
    assert client.get(path, headers=headers).status_code == 404
    assert client.get(f"{path}/events", headers=headers).status_code == 404
    assert client.post(
        f"{path}/commands", json={"message": "Change it", "idempotency_key": "other"}, headers=headers,
    ).status_code == 404
    assert client.post(f"{path}/cancel", headers=headers).status_code == 404
    with patch.object(opencode_api, "get_project_identity", return_value={"owner_user_id": "owner", "status": "active"}):
        assert client.post(
            "/opencode/sessions", json={"connector_id": "mini-pc-1", "project_id": session["project_id"]}, headers=headers,
        ).status_code == 404
        history_path = f"/opencode/projects/{session['project_id']}/history"
        assert client.get(history_path, headers=headers).status_code == 404
        assert client.get(history_path).status_code == 401
        history = client.get(history_path, headers={"Authorization": "Bearer owner"})
        assert history.status_code == 200
        assert history.json()["messages"] == []
        assert history.headers["cache-control"] == "private, no-store"


def test_runtime_config_enables_authoring_only_for_signed_in_users(authoring_client):
    client, _ = authoring_client
    with patch.object(main, "_runtime_config_settings", return_value=None), patch.object(
        main.HardwarePipelineOrchestrator, "get_debug_config", return_value={"live_generation_enabled": False}
    ), patch.object(main, "get_image_output_debug_config", return_value={}), patch.object(
        main, "get_database_config", return_value={"client": None}
    ), patch.object(main.GMICloudProvider, "get_debug_config", return_value={}), patch.object(
        main.FireworksVideoReviewClient, "get_debug_config", return_value={}
    ):
        signed_in = client.get("/runtime/config", headers={"Authorization": "Bearer new-user"})
        signed_out = client.get("/runtime/config")
    assert signed_in.status_code == 200, signed_in.text
    assert signed_out.status_code == 200, signed_out.text
    assert signed_in.json()["deployment"]["authoring_mode_enabled"] is True
    assert signed_in.json()["deployment"]["authoring_access"] is True
    assert signed_out.json()["deployment"]["authoring_access"] is False
