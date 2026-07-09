from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from blueprint_core.continuous_agents import ContinuousAgentCoordinator, JsonlStreamStore, MediaInspector


def write_stream_event(path: Path, *, content: str, event_id: str | None = None) -> None:
    event = {
        "schema_version": 1,
        "event_id": event_id or f"event-{uuid.uuid4().hex}",
        "observed_at_unix_ms": 1,
        "kind": "llm.test.chunk",
        "source": {
            "provider": "test",
            "source_type": "llm.stream",
            "name": "unit",
            "uri": None,
        },
        "payload": {
            "sequence": 1,
            "content": content,
            "done": True,
        },
        "metadata": {},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def write_failed_stream_event(path: Path, *, error_message: str, event_id: str | None = None) -> None:
    event = {
        "schema_version": 1,
        "event_id": event_id or f"event-{uuid.uuid4().hex}",
        "observed_at_unix_ms": 1,
        "kind": "llm.openai.failed",
        "source": {
            "provider": "openai",
            "source_type": "llm.stream",
            "name": "gpt-test",
            "uri": None,
        },
        "payload": {
            "sequence": 1,
            "content": "",
            "done": True,
        },
        "metadata": {
            "error_message": error_message,
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


class ContinuousAgentTests(unittest.TestCase):
    def test_cycle_reads_stream_and_writes_agent_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "unit-stream")
            store.ensure()
            write_stream_event(store.events_path, content="unknown blue device")

            coordinator = ContinuousAgentCoordinator(store, poll_interval_seconds=0.01)
            coordinator.run(max_cycles=1)

            reader_output = store.agent_path("reader").read_text(encoding="utf-8")
            reviewer_output = store.agent_path("reviewer").read_text(encoding="utf-8")
            iterator_output = store.agent_path("prompt-iterator").read_text(encoding="utf-8")

            self.assertIn("agent.reader.batch", reader_output)
            self.assertIn("placeholder_text", reviewer_output)
            self.assertIn("agent.prompt_iteration.proposal", iterator_output)

    def test_cycle_marks_llm_stream_errors_as_reviewer_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "unit-stream-error")
            store.ensure()
            write_failed_stream_event(store.events_path, error_message="OpenAI response incomplete: max_output_tokens.")

            coordinator = ContinuousAgentCoordinator(store, poll_interval_seconds=0.01)
            coordinator.run(max_cycles=1)

            reviewer_output = store.agent_path("reviewer").read_text(encoding="utf-8")
            self.assertIn("llm_stream_error", reviewer_output)
            self.assertIn("llm_stream_failed", reviewer_output)

    def test_image_inspector_reports_missing_and_low_resolution_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing = root / "missing.png"

            from PIL import Image

            low_res = root / "tiny.png"
            Image.new("RGB", (64, 64), color=(0, 0, 255)).save(low_res)

            inspector = MediaInspector()
            missing_report = inspector.inspect_image(missing)
            low_res_report = inspector.inspect_image(low_res)

            self.assertFalse(missing_report.exists)
            self.assertEqual("image_missing", missing_report.findings[0].code)
            self.assertTrue(low_res_report.exists)
            self.assertIn("image_low_resolution", [finding.code for finding in low_res_report.findings])


if __name__ == "__main__":
    unittest.main()
