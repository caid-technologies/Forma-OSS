from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend import storage


SUPABASE_ENV = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
}


class ImageStorageSelectionTests(unittest.TestCase):
    def test_sqlite_database_does_not_enable_supabase_image_storage_from_credentials(self) -> None:
        with patch.dict(os.environ, {"DATABASE_BACKEND": "sqlite", **SUPABASE_ENV}, clear=True):
            config = storage.get_image_storage_config()

        self.assertFalse(config["enabled"])
        self.assertEqual("sqlite-inline", config["provider"])
        self.assertIsNone(config["write_method"])
        self.assertEqual("primary-database", config["selection_source"])

    def test_sqlite_database_can_explicitly_opt_into_supabase_image_storage(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "BLUEPRINT_IMAGE_STORAGE_BACKEND": "supabase",
                **SUPABASE_ENV,
            },
            clear=True,
        ):
            config = storage.get_image_storage_config()

        self.assertTrue(config["enabled"])
        self.assertEqual("supabase-client", config["write_method"])
        self.assertEqual("BLUEPRINT_IMAGE_STORAGE_BACKEND", config["selection_source"])

    def test_supabase_database_preserves_supabase_image_storage_default(self) -> None:
        with patch.dict(os.environ, {"DATABASE_BACKEND": "supabase", **SUPABASE_ENV}, clear=True):
            config = storage.get_image_storage_config()

        self.assertTrue(config["enabled"])
        self.assertEqual("supabase-client", config["write_method"])

    def test_dev_mode_keeps_image_storage_local_despite_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEV_MODE": "true",
                "DATABASE_BACKEND": "supabase",
                "BLUEPRINT_IMAGE_STORAGE_BACKEND": "supabase",
                **SUPABASE_ENV,
            },
            clear=True,
        ):
            config = storage.get_image_storage_config()

        self.assertFalse(config["enabled"])
        self.assertTrue(config["dev_mode"])
        self.assertEqual("BLUEPRINT_DEV_MODE", config["selection_source"])

    def test_sqlite_hydration_never_constructs_a_supabase_storage_client(self) -> None:
        with patch.dict(os.environ, {"DATABASE_BACKEND": "sqlite", **SUPABASE_ENV}, clear=True), patch.object(
            storage,
            "_supabase_storage_bucket",
        ) as storage_bucket:
            metadata = {"project_id": "123", "product_image_s3_key": "images/123/product.png"}
            hydrated = storage.hydrate_image_storage_metadata(metadata, "123")

        self.assertEqual(metadata, hydrated)
        storage_bucket.assert_not_called()


if __name__ == "__main__":
    unittest.main()
