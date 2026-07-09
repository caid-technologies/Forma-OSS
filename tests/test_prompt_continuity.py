from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blueprint_core.agents.firecrawl_mcp import FirecrawlResearchResult, FirecrawlSearchHit
from blueprint_core.continuous_agents import JsonlStreamStore
from blueprint_core.prompt_continuity import (
    DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS,
    DEFAULT_PROMPT_BATCH_MODEL,
    FirecrawlPromptBatchSeeder,
    PromptContinuityReviewer,
    default_prompt_seeds,
)


class FakeFirecrawlClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def research(self, queries):
        self.queries = list(queries)
        return FirecrawlResearchResult(
            configured=True,
            searches_attempted=len(self.queries),
            tool_name="firecrawl_search",
            hits=[
                FirecrawlSearchHit(
                    title="Environmental monitor reference",
                    url="https://example.com/monitor",
                    content="Use vents, a display window, I2C sensors, and a stable enclosure.",
                )
            ],
        )


class PromptContinuityTests(unittest.TestCase):
    def test_default_prompt_batch_has_ten_prompts(self) -> None:
        seeds = default_prompt_seeds()

        self.assertEqual(10, len(seeds))
        self.assertEqual(tuple(range(1, 11)), tuple(seed.index for seed in seeds))

    def test_seeder_records_initial_jobs_and_repaired_children(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "prompt-batch-unit")
            fake_firecrawl = FakeFirecrawlClient()
            seeder = FirecrawlPromptBatchSeeder(
                store=store,
                model=DEFAULT_PROMPT_BATCH_MODEL,
                firecrawl_client=fake_firecrawl,
            )

            report = seeder.seed_and_review(write_report_dir=store.stream_dir / "reports")
            jobs = seeder.queue.jobs()
            results = seeder.queue.results()

            self.assertEqual(10, report.initial_job_count)
            self.assertEqual(10, report.repaired_job_count)
            self.assertEqual(10, len(fake_firecrawl.queries))
            self.assertEqual(20, len(jobs))
            self.assertEqual(10, len(results))
            self.assertEqual("superseded", results[0].status)
            self.assertEqual(jobs[1].job_id, results[0].child_job_id)
            self.assertEqual("prompt-continuity-reviewer", jobs[1].created_by)
            self.assertEqual(DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS, jobs[1].max_output_tokens)
            self.assertIn("Continuity contract", jobs[1].prompt)
            self.assertIn("Firecrawl source context", jobs[1].prompt)
            self.assertEqual("firecrawl_search", jobs[1].metadata.firecrawl.tool_name)
            self.assertTrue(report.report_path and report.report_path.exists())

    def test_reviewer_passes_repaired_prompt_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "prompt-review-unit")
            seeder = FirecrawlPromptBatchSeeder(
                store=store,
                model=DEFAULT_PROMPT_BATCH_MODEL,
                firecrawl_client=FakeFirecrawlClient(),
            )
            seeder.seed_and_review()
            repaired_job = seeder.queue.jobs()[1]

            review = PromptContinuityReviewer().review(repaired_job)

            self.assertTrue(review.passed)
            self.assertEqual((), review.findings)


if __name__ == "__main__":
    unittest.main()
