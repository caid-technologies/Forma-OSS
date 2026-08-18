from __future__ import annotations

import io
import json
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

from apps.api.contribution_export_api import (
    build_contribution_xlsx,
    build_contribution_zip,
    contribution_export_inventory,
    exportable_contribution_records,
)
from blueprint_core import database
from blueprint_core.persistence.providers import create_sqlite_provider
from blueprint_core.persistence.repositories import SqlAlchemyRepository


class ContributionExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        provider = create_sqlite_provider(
            source="contribution export test",
            url=f"sqlite:///{Path(self.directory.name) / 'blueprint.db'}",
            import_legacy_jobs=False,
        )
        assert provider.session_factory is not None
        provider.initialize()
        self.original_provider = database._DATABASE_PROVIDER
        self.original_repository = database._DATABASE_REPOSITORY
        database._DATABASE_PROVIDER = provider
        database._DATABASE_REPOSITORY = SqlAlchemyRepository(provider.session_factory)
        self.project_id = str(uuid.uuid4())
        self.owner_id = "consenting-user@example.com"
        database.save_generated_project(
            project_id=self.project_id,
            title="Secret customer prototype",
            prompt="Contact alice@example.com with token sk-secret and private details",
            hardware_ir={
                "components": [
                    {
                        "ref_des": "U1",
                        "part_number": "MCU-PRIVATE",
                        "name": "Private controller",
                        "category": "Microcontroller",
                        "rationale": "private rationale",
                        "pins": [
                            {"pin_id": "1", "name": "A", "pin_type": "Digital"},
                            {"pin_id": "2", "name": "B", "pin_type": "Digital"},
                        ],
                    },
                    {
                        "ref_des": "S1",
                        "part_number": "SENSOR-PRIVATE",
                        "name": "Private sensor",
                        "category": "Sensor",
                        "rationale": "private rationale",
                        "pins": [],
                    },
                ],
                "nets": [
                    {
                        "net_id": "private-net",
                        "name": "Private net",
                        "net_type": "Digital",
                        "pins": [{"ref_des": "U1", "pin_id": "1"}, {"ref_des": "S1", "pin_id": "1"}],
                    }
                ],
                "validation": {
                    "critical": [],
                    "warning": [
                        {
                            "severity": "WARNING",
                            "category": "Private",
                            "description": "private warning",
                            "troubleshooting": "private fix",
                        }
                    ],
                },
                "assembly_metadata": {
                    "project_id": self.project_id,
                    "chat_id": "private-chat",
                    "source_prompt": "private prompt",
                    "image_url": "https://example.com/private.png",
                },
                "is_valid": True,
            },
            created_at="2026-08-01T00:00:00Z",
            chat_id="private-chat",
            owner_user_id=self.owner_id,
            visibility="private",
        )
    def tearDown(self) -> None:
        database._DATABASE_PROVIDER = self.original_provider
        database._DATABASE_REPOSITORY = self.original_repository
        self.directory.cleanup()

    def test_export_anonymizes_default_opted_in_project_at_download_time(self) -> None:
        inventory = contribution_export_inventory()
        first_export = exportable_contribution_records()
        second_export = exportable_contribution_records()

        self.assertEqual(1, inventory["count"])
        self.assertEqual(
            {
                "file_number",
                "component_count",
                "net_count",
            },
            set(inventory["files"][0]),
        )
        self.assertEqual(1, len(first_export))
        self.assertNotEqual(first_export[0]["dataset_record_id"], second_export[0]["dataset_record_id"])
        serialized = json.dumps(first_export)
        for forbidden in (
            self.project_id,
            self.owner_id,
            "alice@example.com",
            "sk-secret",
            "Secret customer prototype",
            "Private controller",
            "private-chat",
            "example.com",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(2, first_export[0]["payload"]["hardware_summary"]["component_count"])

    def test_account_opt_out_excludes_all_projects(self) -> None:
        database.set_user_model_training_preference(
            self.owner_id,
            allow_model_training=False,
            updated_at="2026-08-11T00:00:00Z",
        )

        self.assertEqual({"count": 0, "files": []}, contribution_export_inventory())
        self.assertEqual([], exportable_contribution_records())

    def test_explicit_account_opt_in_is_included(self) -> None:
        database.set_user_model_training_preference(
            self.owner_id,
            allow_model_training=True,
            updated_at="2026-08-11T00:00:00Z",
        )

        self.assertEqual(1, contribution_export_inventory()["count"])

    def test_export_includes_projects_from_every_non_opted_out_user(self) -> None:
        database.save_generated_project(
            project_id=str(uuid.uuid4()),
            title="Another user's project",
            prompt="private",
            hardware_ir={"components": [], "nets": [], "validation": {}, "is_valid": True},
            created_at="2026-08-02T00:00:00Z",
            owner_user_id="another-user@example.com",
            visibility="private",
        )

        self.assertEqual(2, contribution_export_inventory()["count"])
        self.assertEqual(2, len(exportable_contribution_records()))

    def test_zip_contains_anonymous_numbered_files_and_manifests(self) -> None:
        records = exportable_contribution_records()

        archive_bytes = build_contribution_zip(records, "2026-08-11T12:00:00Z")

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertEqual(
                {"export.json", "manifest.csv", "files/contribution-00001.json"},
                set(archive.namelist()),
            )
            exported = json.loads(archive.read("files/contribution-00001.json"))
            self.assertEqual(2, exported["payload"]["hardware_summary"]["component_count"])
            export_metadata = json.loads(archive.read("export.json"))
            self.assertEqual("performed during export", export_metadata["anonymization"])

    def test_xlsx_is_a_valid_office_archive_with_anonymous_rows(self) -> None:
        workbook_bytes = build_contribution_xlsx(exportable_contribution_records())

        with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
            self.assertIn("xl/workbook.xml", workbook.namelist())
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("dataset_record_id", sheet)
            self.assertIn("component_count", sheet)
            self.assertNotIn(self.owner_id, sheet)
            self.assertNotIn(self.project_id, sheet)


if __name__ == "__main__":
    unittest.main()
