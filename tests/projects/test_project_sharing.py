"""Authorization and immutable-version regression coverage for public links."""
from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from apps.api.project_share_api import router
from tests.projects import test_project_history


class ProjectSharingTests(test_project_history.ProjectVersionHistoryTests):
    """Exercise capabilities against actual SQLite revision persistence."""

    def setUp(self) -> None:
        """Create three versions and install the public sharing routes."""
        super().setUp()
        self.client.app.include_router(router)
        self.enterContext(patch.dict(os.environ, {"FORMA_PROJECT_SHARE_SECRET": "s" * 64}))
        self.shared = f"/projects/{self.project_id}/shared"

    def issue(self, index: int = 0) -> dict[str, str]:
        """Issue a capability while acting as the project owner."""
        response = self.client.post(f"{self.shared}/{self.revisions[index].revision_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return {"X-Project-Share": response.json()["token"]}

    def test_anonymous_link_is_pinned_and_cannot_list_history(self) -> None:
        """Later saves do not change the version or broaden a recipient's access."""
        headers = self.issue()
        self.user = replace(self.user, owner_user_id="", is_authenticated=False)
        self.save("A newer private design")
        response = self.client.get(f"{self.shared}/{self.revisions[0].revision_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["revision"], 1)
        self.assertEqual(response.json()["title"], "Base")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(self.client.get(self.url, headers=headers).status_code, 401)
        self.assertEqual(self.client.get(f"{self.url}/{self.revisions[0].revision_id}", headers=headers).status_code, 401)
        self.assertEqual(self.client.post(f"{self.shared}/{self.revisions[1].revision_id}", headers=headers).status_code, 401)

    def test_token_cannot_be_reused_for_another_revision_or_project(self) -> None:
        """A share capability is scoped to exactly one project and revision."""
        headers = self.issue()
        first = f"{self.shared}/{self.revisions[0].revision_id}"
        self.assertEqual(self.client.get(first).status_code, 404)
        self.assertEqual(self.client.get(first, headers={"X-Project-Share": "0" * 64}).status_code, 404)
        self.assertEqual(self.client.get(f"{self.shared}/{self.revisions[1].revision_id}", headers=headers).status_code, 404)
        other = str(uuid4())
        self.assertEqual(self.client.get(first.replace(self.project_id, other), headers=headers).status_code, 404)
        self.user = replace(self.user, owner_user_id="another-owner")
        self.assertEqual(self.client.post(first).status_code, 404)
        with patch("apps.api.project_share_api.get_project_identity", return_value={"owner_user_id": self.owner, "status": "deletion_pending"}):
            self.assertEqual(self.client.get(first, headers=headers).status_code, 404)

    def test_shared_projection_omits_private_provenance(self) -> None:
        """Internal generation metadata and instructions never leave the share API."""
        headers = self.issue()
        private = {"chat_id": "secret-chat", "last_iteration": {"instruction": "private prompt"},
                   "reference_image_url": "private-upload", "product_image_url": "https://example.test/design.png",
                   "product_visual_sequence": [{"url": "https://example.test/side.png", "prompt": "secret image prompt"}]}
        with patch("apps.api.project_history_api.hydrate_image_storage_metadata", return_value=private):
            response = self.client.get(f"{self.shared}/{self.revisions[0].revision_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("secret", response.text)
        self.assertNotIn("private prompt", response.text)
        self.assertNotIn("private-upload", response.text)
        self.assertEqual(response.json()["project_ir"]["project_version_history"], [])
        self.assertEqual(response.json()["project_ir"]["assembly_metadata"]["product_image_url"], "https://example.test/design.png")

    def test_shared_cad_is_bound_to_version_and_checksum(self) -> None:
        """Anonymous CAD reads use the same capability and artifact checksum."""
        content = b"saved STEP bytes"
        digest = hashlib.sha256(content).hexdigest()
        old = self.save("Shared CAD", cad={"stored_sha256": digest})
        headers = self.issue(-1)
        self.save("Later CAD", cad={"stored_sha256": "b" * 64})
        url = f"{self.shared}/{old.revision_id}/cad/{digest}"
        with patch("apps.api.project_history_api.ProjectArtifactStorage.get", return_value=SimpleNamespace(content=content)) as storage:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.get(url.replace(digest, "b" * 64), headers=headers).status_code, 404)
            self.assertEqual(self.client.get(url, headers=headers).content, content)
            storage.assert_called_once_with(self.project_id, digest, "model/step")

    def test_missing_key_fails_closed_and_rotation_invalidates_links(self) -> None:
        """Sharing requires an operator-supplied secret stable across replicas."""
        headers = self.issue()
        url = f"{self.shared}/{self.revisions[0].revision_id}"
        with patch.dict(os.environ, {"FORMA_PROJECT_SHARE_SECRET": ""}):
            self.assertEqual(self.client.post(url).status_code, 503)
        with patch.dict(os.environ, {"FORMA_PROJECT_SHARE_SECRET": "different" * 8}):
            self.assertEqual(self.client.get(url, headers=headers).status_code, 404)
