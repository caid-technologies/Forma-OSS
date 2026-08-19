from __future__ import annotations

import unittest

from evals.quality.design_generation_benchmark import (
    GenerationBenchmarkAttempt,
    summarize_attempts,
)


class DesignGenerationBenchmarkTests(unittest.TestCase):
    def test_reports_yield_failure_coverage_and_partial_retention(self) -> None:
        summary = summarize_attempts(
            [
                GenerationBenchmarkAttempt(
                    pipeline="intent-first",
                    prompt="one",
                    status="complete",
                    valid_bom_line_count=10,
                    physical_component_count=14,
                    required_capability_count=4,
                    covered_capability_count=4,
                    required_obligation_count=5,
                    resolved_obligation_count=5,
                    deferred_role_count=0,
                    blocked_role_count=0,
                    localized_retry_count=1,
                ),
                GenerationBenchmarkAttempt(
                    pipeline="intent-first",
                    prompt="two",
                    status="partial",
                    valid_bom_line_count=8,
                    physical_component_count=11,
                    required_capability_count=4,
                    covered_capability_count=3,
                    required_obligation_count=5,
                    resolved_obligation_count=4,
                    deferred_role_count=1,
                    blocked_role_count=0,
                    localized_retry_count=2,
                    partial_retained_useful_bom=True,
                ),
            ]
        )

        self.assertEqual(9.0, summary.valid_bom_yield)
        self.assertEqual(0.0, summary.generation_failure_rate)
        self.assertEqual(0.9, summary.required_obligation_coverage)
        self.assertEqual(0.875, summary.required_capability_coverage)
        self.assertEqual(0.9, summary.resolved_obligation_coverage)
        self.assertEqual(1.0, summary.partial_project_bom_retention_rate)
        self.assertEqual(3, summary.localized_retry_count)


if __name__ == "__main__":
    unittest.main()
