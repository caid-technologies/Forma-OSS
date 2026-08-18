from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from blueprint_core import database
from blueprint_core.runtime import primary_database_backend_from_environment


class DatabaseConfigSelectionTests(unittest.TestCase):
    def test_pure_backend_resolver_matches_local_supabase_dev_selection(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEV_MODE": "true",
                "DATABASE_BACKEND": "supabase",
                "SUPABASE_URL": "http://127.0.0.1:54321",
                "SUPABASE_SERVICE_ROLE_KEY": "local-service-role",
            },
            clear=True,
        ):
            self.assertEqual("supabase", primary_database_backend_from_environment())

    def test_dev_mode_allows_local_supabase_backend(self) -> None:
        fake_client = object()
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEV_MODE": "true",
                "DATABASE_BACKEND": "supabase",
                "SUPABASE_URL": "http://127.0.0.1:54321",
                "SUPABASE_SERVICE_ROLE_KEY": "local-service-role",
            },
            clear=True,
        ), patch.object(database, "_build_supabase_client", return_value=fake_client) as build_client:
            config, engine, client = database._select_database_config()

        self.assertEqual("supabase", config.backend)
        self.assertEqual("SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY", config.source)
        self.assertIsNone(engine)
        self.assertIs(client, fake_client)
        build_client.assert_called_once_with("http://127.0.0.1:54321", "local-service-role")

    def test_dev_mode_keeps_remote_supabase_on_sqlite(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEV_MODE": "true",
                "DATABASE_BACKEND": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "remote-service-role",
            },
            clear=True,
        ), patch.object(database, "_build_supabase_client") as build_client:
            config, engine, client = database._select_database_config()

        self.assertEqual("sqlite", config.backend)
        self.assertEqual("BLUEPRINT_DEV_MODE", config.source)
        self.assertIsNotNone(engine)
        self.assertIsNone(client)
        build_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
