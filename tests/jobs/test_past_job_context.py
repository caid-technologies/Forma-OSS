from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from blueprint_core.jobs.context import (
    PastJobContextSource,
    compose_prompt_with_past_jobs,
    normalize_generation_data_sources,
)
from blueprint_core.jobs.source_usage import infer_source_usage, normalize_source_usage
from blueprint_core.workspaces.projects.models import GenerateProjectRequest


class FakeJobStore:
    def __init__(self, jobs):
        self.jobs = jobs

    def list_jobs(self, *, sender=None, status=None, limit=50):
        del sender
        return [job for job in self.jobs if status is None or job.get("status") == status][:limit]


def project(project_id: str, owner: str, prompt: str, title: str, part_number: str):
    return SimpleNamespace(
        project_id=project_id,
        owner_user_id=owner,
        prompt=prompt,
        title=title,
        hardware_ir={
            "overview": {"title": title, "description": f"A buildable {title}"},
            "requirements": {"requirements": [prompt], "operating_voltage": 3.3},
            "components": [{"part_number": part_number, "name": part_number, "category": "Sensor"}],
            "constraints": ["low voltage"],
            "validation": {"critical": [], "warning": []},
            "is_valid": True,
        },
    )


class PastJobContextTests(unittest.TestCase):
    def test_request_normalizes_past_jobs_source(self) -> None:
        request = GenerateProjectRequest(prompt="build a sensor", data_sources=["history"], past_jobs_limit=2)

        self.assertEqual(["past_jobs"], request.data_sources)
        self.assertEqual(2, request.past_jobs_limit)
        self.assertEqual(["past_jobs"], normalize_generation_data_sources(["past-jobs", "past_jobs"]))

    def test_retrieval_is_owner_scoped_and_prefers_relevant_outputs(self) -> None:
        projects = {
            "plant": project("plant", "user-a", "soil moisture plant monitor", "Plant Monitor", "SEN-MOISTURE"),
            "lamp": project("lamp", "user-a", "desk lamp", "Desk Lamp", "LED-WHITE"),
            "other": project("other", "user-b", "soil moisture monitor", "Private Monitor", "PRIVATE-PART"),
        }
        jobs = [
            {
                "job_id": "job-lamp",
                "action": "blueprint.generate_project",
                "status": "succeeded",
                "created_at": "2026-07-30T12:03:00Z",
                "payload": {"owner_user_id": "user-a"},
                "result_summary": {"project_id": "lamp"},
            },
            {
                "job_id": "job-other",
                "action": "blueprint.generate_project",
                "status": "succeeded",
                "created_at": "2026-07-30T12:02:00Z",
                "payload": {"owner_user_id": "user-b"},
                "result_summary": {"project_id": "other"},
            },
            {
                "job_id": "job-plant",
                "action": "blueprint.generate_project",
                "status": "succeeded",
                "created_at": "2026-07-30T12:01:00Z",
                "payload": {"owner_user_id": "user-a"},
                "result_summary": {"project_id": "plant"},
            },
        ]
        source = PastJobContextSource(FakeJobStore(jobs), projects.get)

        context = asyncio.run(source.retrieve("new soil moisture controller", owner_user_id="user-a", limit=2))

        self.assertEqual(["job-plant", "job-lamp"], [item.job_id for item in context.items])
        prompt = compose_prompt_with_past_jobs("Build it", context)
        self.assertIn("PAST JOB OUTPUT CONTEXT", prompt)
        self.assertIn("SEN-MOISTURE", prompt)
        self.assertNotIn("PRIVATE-PART", prompt)

    def test_retrieval_without_owner_returns_no_context(self) -> None:
        context = asyncio.run(PastJobContextSource(FakeJobStore([]), lambda _project_id: None).retrieve("x", owner_user_id=None))

        self.assertFalse(context.used)
        self.assertIn("authenticated", context.reason or "")

    def test_source_usage_tracks_past_jobs(self) -> None:
        requested = infer_source_usage(
            action="blueprint.generate_project",
            payload={"workflow": "default", "data_sources": ["past_jobs"]},
        )
        used = normalize_source_usage({"workflow": "default", "past_jobs": True})

        self.assertTrue(requested["past_jobs"])
        self.assertIn("past_jobs", requested["sources"])
        self.assertTrue(used["job_history"])


if __name__ == "__main__":
    unittest.main()
