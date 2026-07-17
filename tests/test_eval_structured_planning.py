"""Gate tests for the structured-planning eval's outcome classification.

The eval itself is a paid periodic run; these verify its deterministic plumbing
(outcome bucketing from repair-layer logs) without any live LLM call.
"""
from __future__ import annotations

import logging
import unittest

from benchmarks.eval_structured_planning import REPAIR_LOGGER, run_case


class _StubProvider:
    def __init__(self, *, log_message: str | None = None, error: Exception | None = None):
        self._log_message = log_message
        self._error = error

    def generate_structured(self, prompt, schema_class):
        if self._log_message:
            logging.getLogger(REPAIR_LOGGER).warning(self._log_message)
        if self._error:
            raise self._error
        return object()


class EvalStructuredPlanningTests(unittest.TestCase):
    def test_clean_success_is_valid_first_parse(self) -> None:
        case = run_case(_StubProvider(), "plan a clock")
        self.assertEqual("valid_first_parse", case["outcome"])
        self.assertIsNone(case["error"])

    def test_renest_warning_is_valid_after_repair(self) -> None:
        case = run_case(
            _StubProvider(log_message="Structured output for WebProjectPlan required flat-field re-nesting: x"),
            "plan a clock",
        )
        self.assertEqual("valid_after_repair", case["outcome"])
        self.assertTrue(case["renested"])
        self.assertFalse(case["salvaged"])

    def test_salvage_warning_is_valid_after_repair(self) -> None:
        case = run_case(
            _StubProvider(log_message="Structured output for WebProjectPlan required JSON salvage (10 chars): x"),
            "plan a clock",
        )
        self.assertEqual("valid_after_repair", case["outcome"])
        self.assertTrue(case["salvaged"])

    def test_exception_is_failed(self) -> None:
        case = run_case(_StubProvider(error=RuntimeError("boom")), "plan a clock")
        self.assertEqual("failed", case["outcome"])
        self.assertIn("boom", case["error"])


if __name__ == "__main__":
    unittest.main()
