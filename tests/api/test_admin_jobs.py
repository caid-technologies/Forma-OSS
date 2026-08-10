from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.api.main import _admin_job_records, list_a2a_jobs
from apps.api.auth import UserContext


ADMIN = UserContext(
    provider="clerk",
    subject="admin_1",
    owner_user_id="admin_1",
    is_authenticated=True,
    is_admin=True,
    claims={"sub": "admin_1"},
)


class AdminJobsTests(unittest.TestCase):
    def test_admin_job_records_expose_owner_and_profile_without_mutating_job(self) -> None:
        job = {
            "job_id": "job_1",
            "payload": {"owner_user_id": "user_1", "prompt": "Build a weather station"},
        }

        with patch(
            "apps.api.main.clerk_user_profile",
            return_value={"display_name": "Ada", "email": "ada@example.com", "image_url": None},
        ):
            records = _admin_job_records([job])

        self.assertNotIn("owner_user_id", job)
        self.assertEqual("user_1", records[0]["owner_user_id"])
        self.assertEqual("Ada", records[0]["owner_display_name"])
        self.assertEqual("ada@example.com", records[0]["owner_email"])
        self.assertEqual("Build a weather station", records[0]["payload"]["prompt"])

    def test_admin_job_records_keep_unowned_jobs_visible(self) -> None:
        records = _admin_job_records([{"job_id": "job_script", "payload": {"prompt": "Example"}}])

        self.assertIsNone(records[0]["owner_user_id"])
        self.assertIsNone(records[0]["owner_display_name"])
        self.assertIsNone(records[0]["owner_email"])

    def test_admin_jobs_endpoint_returns_enriched_records(self) -> None:
        jobs = [{"job_id": "job_2", "payload": {"owner_user_id": "user_2", "prompt": "Make an alarm"}}]

        with patch("apps.api.main.JOB_STORE.list_jobs", return_value=jobs) as list_jobs, patch(
            "apps.api.main.clerk_user_profile", return_value=None
        ):
            response = list_a2a_jobs(sender=None, job_status="running", limit=25, _user=ADMIN)

        list_jobs.assert_called_once_with(sender=None, status="running", limit=25)
        self.assertEqual("user_2", response[0]["owner_user_id"])
        self.assertEqual("Make an alarm", response[0]["payload"]["prompt"])


if __name__ == "__main__":
    unittest.main()
