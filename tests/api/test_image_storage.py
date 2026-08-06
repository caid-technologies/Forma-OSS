from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from apps.api import storage


SUPABASE_ENV = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
}


class ImageStorageSelectionTests(unittest.TestCase):
    def test_sqlite_database_does_not_enable_supabase_image_storage_from_credentials(self) -> None:
        with patch.dict(os.environ, {"DATABASE_BACKEND": "sqlite", **SUPABASE_ENV}, clear=True):
            config = storage.get_image_storage_config()

        self.assertFalse(config["enabled"])
        self.assertEqual("database-inline", config["provider"])
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
        self.assertEqual(
            "https://example.storage.supabase.co/storage/v1/s3",
            config["endpoint"],
        )
        self.assertEqual("BLUEPRINT_IMAGE_STORAGE_BACKEND", config["selection_source"])

    def test_custom_supabase_url_derives_its_own_storage_endpoint(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "supabase",
                "SUPABASE_URL": "http://localhost:54321",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
            },
            clear=True,
        ):
            config = storage.get_image_storage_config()

        self.assertTrue(config["enabled"])
        self.assertEqual("http://localhost:54321/storage/v1/s3", config["endpoint"])

    def test_s3_compatible_storage_requires_an_explicit_endpoint(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "BLUEPRINT_IMAGE_STORAGE_BACKEND": "s3-compatible",
                "SUPABASE_S3_ACCESS_KEY_ID": "access-key",
                "SUPABASE_S3_SECRET_ACCESS_KEY": "secret-key",
            },
            clear=True,
        ):
            config = storage.get_image_storage_config()

        self.assertFalse(config["enabled"])
        self.assertIsNone(config["endpoint"])
        self.assertIn("SUPABASE_S3_ENDPOINT", config["disabled_reason"])

    def test_s3_compatible_storage_uses_the_explicit_endpoint(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "BLUEPRINT_IMAGE_STORAGE_BACKEND": "s3-compatible",
                "SUPABASE_S3_ENDPOINT": "https://storage.example.test/s3",
                "SUPABASE_S3_ACCESS_KEY_ID": "access-key",
                "SUPABASE_S3_SECRET_ACCESS_KEY": "secret-key",
            },
            clear=True,
        ):
            config = storage.get_image_storage_config()

        self.assertTrue(config["enabled"])
        self.assertEqual("s3-compatible", config["write_method"])
        self.assertEqual("https://storage.example.test/s3", config["endpoint"])

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
