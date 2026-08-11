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
        self.snapshot_id = str(uuid.uuid4())
        database.upsert_project_contribution_snapshot(
            {
                "id": self.snapshot_id,
                "source_project_id": str(uuid.uuid4()),
                "consent_record_id": str(uuid.uuid4()),
                "sanitization_version": "2026-07-31.1",
                "contribution_status": "anonymized",
                "payload_json": {
                    "schema_version": 1,
                    "sanitization_version": "2026-07-31.1",
                    "consent_version": "2026-07-31",
                    "permitted_purposes": ["evaluation", "product_research"],
                    "hardware_summary": {
                        "is_valid": True,
                        "component_count": 2,
                        "component_categories": {"sensor": 1, "microcontroller": 1},
                        "component_pin_counts": [8, 2],
                        "net_count": 1,
                        "net_connection_counts": [2],
                        "validation_counts": {"critical": 0, "warnings": 1},
                    },
                },
                "created_at": "2026-08-01T00:00:00Z",
                "sanitized_at": "2026-08-01T00:00:00Z",
                "anonymized_at": "2026-08-02T00:00:00Z",
                "purged_at": None,
            }
        )

    def tearDown(self) -> None:
        database._DATABASE_PROVIDER = self.original_provider
        database._DATABASE_REPOSITORY = self.original_repository
        self.directory.cleanup()

    def test_approved_anonymization_review_is_required_for_export(self) -> None:
        inventory = contribution_export_inventory()
        self.assertEqual(1, inventory["counts"]["pending_review"])
        self.assertEqual(0, inventory["counts"]["exportable"])
        self.assertNotIn("source_project_id", inventory["snapshots"][0])
        self.assertNotIn("consent_record_id", inventory["snapshots"][0])
        self.assertNotIn("reviewed_by_user_id", inventory["snapshots"][0])
        self.assertEqual([], exportable_contribution_records())

        reviewed = database.review_project_contribution_snapshot(
            self.snapshot_id,
            "approved",
            "2026-08-03T00:00:00Z",
            "admin-reviewer",
        )

        self.assertIsNotNone(reviewed)
        records = exportable_contribution_records()
        self.assertEqual(1, len(records))
        self.assertNotIn("admin-reviewer", json.dumps(records))
        self.assertNotIn("source_project_id", json.dumps(records))
        self.assertNotIn("consent_record_id", json.dumps(records))

    def test_rejected_review_is_not_exportable(self) -> None:
        reviewed = database.review_project_contribution_snapshot(
            self.snapshot_id,
            "rejected",
            "2026-08-03T00:00:00Z",
            "admin-reviewer",
        )
        self.assertIsNotNone(reviewed)
        self.assertEqual([], exportable_contribution_records())

    def test_zip_contains_manifest_and_one_json_file_per_record(self) -> None:
        database.review_project_contribution_snapshot(
            self.snapshot_id,
            "approved",
            "2026-08-03T00:00:00Z",
            "admin-reviewer",
        )
        records = exportable_contribution_records()

        archive_bytes = build_contribution_zip(records, "2026-08-11T12:00:00Z")

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertEqual(
                {"export.json", "manifest.csv", f"snapshots/{self.snapshot_id}.json"},
                set(archive.namelist()),
            )
            exported = json.loads(archive.read(f"snapshots/{self.snapshot_id}.json"))
            self.assertEqual(2, exported["payload"]["hardware_summary"]["component_count"])
            self.assertIn(self.snapshot_id, archive.read("manifest.csv").decode("utf-8"))

    def test_xlsx_is_a_valid_office_archive_with_contribution_rows(self) -> None:
        database.review_project_contribution_snapshot(
            self.snapshot_id,
            "approved",
            "2026-08-03T00:00:00Z",
            "admin-reviewer",
        )

        workbook_bytes = build_contribution_xlsx(exportable_contribution_records())

        with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
            self.assertIn("xl/workbook.xml", workbook.namelist())
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("dataset_record_id", sheet)
            self.assertIn(self.snapshot_id, sheet)
            self.assertIn("component_count", sheet)


if __name__ == "__main__":
    unittest.main()
