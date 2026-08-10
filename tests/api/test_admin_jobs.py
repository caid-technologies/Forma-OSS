from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.api.main import _admin_job_records, get_a2a_job_metrics, list_a2a_jobs
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
            return_value={
                "display_name": "Ada Lovelace",
                "email": "ada@example.com",
                "github_username": "ada-l",
                "image_url": None,
            },
        ):
            records = _admin_job_records([job])

        self.assertNotIn("owner_user_id", job)
        self.assertEqual("user_1", records[0]["owner_user_id"])
        self.assertEqual("Ada Lovelace", records[0]["owner_display_name"])
        self.assertEqual("ada@example.com", records[0]["owner_email"])
        self.assertEqual("ada-l", records[0]["owner_github_username"])
        self.assertEqual("ada-l", records[0]["owner_username"])
        self.assertEqual("Build a weather station", records[0]["payload"]["prompt"])

    def test_admin_job_records_use_email_as_username_without_github(self) -> None:
        job = {"job_id": "job_email", "payload": {"owner_user_id": "user_email"}}

        with patch(
            "apps.api.main.clerk_user_profile",
            return_value={
                "display_name": "Grace Hopper",
                "email": "grace@example.com",
                "github_username": None,
                "image_url": None,
            },
        ):
            records = _admin_job_records([job])

        self.assertEqual("grace@example.com", records[0]["owner_username"])

    def test_admin_job_records_keep_unowned_jobs_visible(self) -> None:
        records = _admin_job_records([{"job_id": "job_script", "payload": {"prompt": "Example"}}])

        self.assertIsNone(records[0]["owner_user_id"])
        self.assertIsNone(records[0]["owner_display_name"])
        self.assertIsNone(records[0]["owner_email"])
        self.assertIsNone(records[0]["owner_github_username"])
        self.assertIsNone(records[0]["owner_username"])

    def test_admin_jobs_endpoint_returns_enriched_records(self) -> None:
        jobs = [{"job_id": "job_2", "payload": {"owner_user_id": "user_2", "prompt": "Make an alarm"}}]

        with patch("apps.api.main.JOB_STORE.list_jobs", return_value=jobs) as list_jobs, patch(
            "apps.api.main.clerk_user_profile", return_value=None
        ):
            response = list_a2a_jobs(sender=None, job_status="running", limit=25, _user=ADMIN)

        list_jobs.assert_called_once_with(sender=None, status="running", limit=25)
        self.assertEqual("user_2", response[0]["owner_user_id"])
        self.assertEqual("Make an alarm", response[0]["payload"]["prompt"])

    def test_admin_job_metrics_endpoint_delegates_bounded_windows(self) -> None:
        metrics = {"jobs_today": 3, "jobs_last_hour": 1, "failure_rate": 25.0}

        with patch("apps.api.main.JOB_STORE.get_metrics", return_value=metrics) as get_metrics:
            response = get_a2a_job_metrics(days=7, hours=24, _user=ADMIN)

        get_metrics.assert_called_once_with(days=7, hours=24)
        self.assertEqual(metrics, response)


if __name__ == "__main__":
    unittest.main()
