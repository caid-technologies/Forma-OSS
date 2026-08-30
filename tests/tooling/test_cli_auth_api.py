from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app


class CliAuthApiTests(unittest.TestCase):
    def test_device_flow_can_approve_exchange_and_revoke_in_local_mode(self) -> None:
        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "local", "FORMA_CLI_AUTH_STORAGE": "memory"}, clear=False):
            client = TestClient(app)
            authorization = client.post("/cli/device/authorize", json={})
            self.assertEqual(200, authorization.status_code)
            payload = authorization.json()

            approved = client.post("/cli/device/approve", json={"user_code": payload["user_code"]})
            self.assertEqual(200, approved.status_code)
            self.assertEqual(
                "approved",
                client.post("/cli/device/poll", json={"device_code": payload["device_code"]}).json()["status"],
            )

            token_response = client.post("/cli/device/token", json={"device_code": payload["device_code"]})
            self.assertEqual(200, token_response.status_code)
            tokens = token_response.json()
            self.assertEqual(
                200,
                client.get(
                    "/cli/whoami",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                ).status_code,
            )
            self.assertEqual(200, client.post("/cli/token/revoke", json={"refresh_token": tokens["refresh_token"]}).status_code)
            self.assertEqual(
                401,
                client.get(
                    "/cli/whoami",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                ).status_code,
            )


if __name__ == "__main__":
    unittest.main()
