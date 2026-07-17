from __future__ import annotations

import unittest

from backend.a2a import build_generation_response
from blueprint_core import database


class UserSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database.init_db()

    def test_user_settings_default_to_training_allowed(self) -> None:
        settings = database.get_user_settings("user_settings_default")

        self.assertFalse(settings.model_training_opt_out)

    def test_user_settings_can_opt_out_of_model_training(self) -> None:
        settings = database.upsert_user_settings("user_settings_opt_out", model_training_opt_out=True)

        self.assertTrue(settings.model_training_opt_out)
        payload = database.user_settings_public_payload(settings)
        self.assertTrue(payload["training"]["model_training_opt_out"])

    def test_generation_metadata_records_training_opt_out(self) -> None:
        response = build_generation_response(
            "blink an LED",
            workflow="default",
            provider="simulation",
            model_training_opt_out=True,
            owner_user_id="user_settings_generation",
        )

        metadata = response["project_ir"]["assembly_metadata"]
        self.assertTrue(metadata["model_training_opt_out"])
        self.assertFalse(metadata["training_data_policy"]["allow_model_training"])


if __name__ == "__main__":
    unittest.main()
