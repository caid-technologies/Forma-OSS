import unittest

from fastapi.testclient import TestClient

from apps.api.main import app


class HealthAndCorsTests(unittest.TestCase):
    client = TestClient(app)

    def test_health_is_lightweight(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "healthy"}, response.json())

    def test_cors_allows_production_and_local_origins(self) -> None:
        for origin in ("https://caid-technologies.us", "http://localhost:3000"):
            with self.subTest(origin=origin):
                response = self.client.options(
                    "/projects",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "authorization",
                    },
                )

                self.assertEqual(200, response.status_code)
                self.assertEqual(origin, response.headers["access-control-allow-origin"])
                self.assertEqual("true", response.headers["access-control-allow-credentials"])

    def test_cors_rejects_unapproved_origins(self) -> None:
        response = self.client.options(
            "/projects",
            headers={
                "Origin": "https://unrelated.example",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertNotIn("access-control-allow-origin", response.headers)
