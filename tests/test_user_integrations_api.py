from __future__ import annotations

import unittest

from fastapi.routing import APIRoute

from backend.auth import require_deployed_clerk_auth
from backend.user_integrations_api import router


class UserIntegrationsApiAuthTests(unittest.TestCase):
    def test_user_integration_routes_require_deployed_auth(self) -> None:
        routes = [route for route in router.routes if isinstance(route, APIRoute)]
        self.assertGreaterEqual(len(routes), 4)

        for route in routes:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(require_deployed_clerk_auth, dependency_calls, route.path)


if __name__ == "__main__":
    unittest.main()
