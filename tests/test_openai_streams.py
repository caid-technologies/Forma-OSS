from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from blueprint_core.continuous_openai_jobs import ContinuousOpenAIJobRunner
from blueprint_core.continuous_openai_jobs import ContinuousOpenAIJobQueue, ContinuousOpenAIJobSpec
from blueprint_core.continuous_agents import JsonlStreamStore
from blueprint_core.openai_streams import (
    OpenAICompatibleChatConfig,
    OpenAIStreamConfig,
    OpenAIStreamRequestError,
    OpenAIStreamEventWriter,
    OpenAITextStreamChunk,
    ServerSentEvent,
    chat_completion_sse_chunks,
    iter_sse_events,
    openai_chunk_from_sse,
)


class FakeStreamer:
    def __init__(self, config: OpenAIStreamConfig) -> None:
        self.config = config

    def stream_text(self):
        yield OpenAITextStreamChunk(
            sequence=1,
            content=self.config.prompt,
            done=False,
            response_event_type="response.output_text.delta",
            response_id="resp_fake",
        )
        yield OpenAITextStreamChunk(
            sequence=2,
            content="",
            done=True,
            response_event_type="response.completed",
            response_id="resp_fake",
        )


class FailingStreamer:
    def __init__(self, config: OpenAIStreamConfig) -> None:
        self.config = config

    def stream_text(self):
        raise OpenAIStreamRequestError("POST", "https://api.openai.com/v1/responses", 500, "unit failure")
        yield


class FakeChatStreamer:
    configs: list[OpenAICompatibleChatConfig] = []

    def __init__(self, config: OpenAICompatibleChatConfig) -> None:
        self.config = config
        self.configs.append(config)

    def stream_text(self):
        yield OpenAITextStreamChunk(
            sequence=1,
            content=f"{self.config.provider_name}:{self.config.model}:{self.config.prompt}",
            done=False,
            response_event_type="chat.completion.message",
            response_id="chat_fake",
        )
        yield OpenAITextStreamChunk(
            sequence=2,
            content="",
            done=True,
            response_event_type="chat.completion.stop",
            response_id="chat_fake",
        )


class OpenAIStreamTests(unittest.TestCase):
    def test_chat_completion_sse_chunks_stream_deltas(self) -> None:
        lines = [
            b'data: {"id":"chat_1","choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}\n',
            b"\n",
            b'data: {"id":"chat_1","choices":[{"delta":{"content":"lo"},"finish_reason":null}]}\n',
            b"\n",
            b'data: {"id":"chat_1","choices":[{"delta":{},"finish_reason":"stop"}]}\n',
            b"\n",
        ]

        chunks = list(chat_completion_sse_chunks(lines, provider_name="baseten"))

        self.assertEqual("Hello", "".join(chunk.content for chunk in chunks))
        self.assertTrue(chunks[-1].done)
        self.assertEqual("chat.completion.stop", chunks[-1].response_event_type)

    def test_iter_sse_events_parses_event_and_data_blocks(self) -> None:
        lines = [
            b"event: response.output_text.delta\n",
            b'data: {"type":"response.output_text.delta","delta":"blue"}\n',
            b"\n",
            b"data: [DONE]\n",
            b"\n",
        ]

        events = list(iter_sse_events(lines))

        self.assertEqual(2, len(events))
        self.assertEqual("response.output_text.delta", events[0].event)
        self.assertIn('"delta":"blue"', events[0].data)
        self.assertEqual("[DONE]", events[1].data)

    def test_openai_chunk_from_sse_extracts_delta_and_completion(self) -> None:
        delta = openai_chunk_from_sse(
            ServerSentEvent(
                event="response.output_text.delta",
                data=json.dumps({"type": "response.output_text.delta", "delta": "blue", "response_id": "resp_123"}),
            ),
            sequence=1,
        )
        completed = openai_chunk_from_sse(
            ServerSentEvent(event="response.completed", data=json.dumps({"type": "response.completed", "response": {"id": "resp_123"}})),
            sequence=2,
        )

        self.assertIsNotNone(delta)
        self.assertEqual("blue", delta.content)
        self.assertFalse(delta.done)
        self.assertIsNotNone(completed)
        self.assertTrue(completed.done)
        self.assertEqual("resp_123", completed.response_id)

    def test_openai_chunk_from_sse_explains_max_output_incomplete(self) -> None:
        chunk = openai_chunk_from_sse(
            ServerSentEvent(
                event="response.incomplete",
                data=json.dumps(
                    {
                        "type": "response.incomplete",
                        "response": {
                            "id": "resp_123",
                            "incomplete_details": {"reason": "max_output_tokens"},
                        },
                    }
                ),
            ),
            sequence=1,
        )

        self.assertIsNotNone(chunk)
        self.assertTrue(chunk.done)
        self.assertIn("max_output_tokens", chunk.error_message or "")
        self.assertIn("Increase", chunk.error_message or "")

    def test_writer_appends_openai_chunks_to_stream_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "openai-unit")
            writer = OpenAIStreamEventWriter(store)

            event_id = writer.append(
                OpenAITextStreamChunk(
                    sequence=1,
                    content="blue",
                    done=False,
                    response_event_type="response.output_text.delta",
                    response_id="resp_123",
                ),
                model="gpt-5.5",
                base_url="https://api.openai.com/v1",
            )

            line = store.events_path.read_text(encoding="utf-8").strip()
            payload = json.loads(line)
            self.assertTrue(event_id.startswith("openai-"))
            self.assertEqual("llm.openai.delta", payload["kind"])
            self.assertEqual("openai", payload["source"]["provider"])
            self.assertEqual("blue", payload["payload"]["content"])

    def test_writer_can_label_baseten_stream_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "baseten-unit")
            writer = OpenAIStreamEventWriter(
                store,
                provider_name="baseten",
                event_provider_name="baseten",
                endpoint_path="chat/completions",
            )

            event_id = writer.append(
                OpenAITextStreamChunk(
                    sequence=1,
                    content="blue",
                    done=False,
                    response_event_type="chat.completion.message",
                    response_id="chat_123",
                ),
                model="zai-org/GLM-5.2",
                base_url="https://inference.baseten.co/v1",
            )

            payload = json.loads(store.events_path.read_text(encoding="utf-8").strip())
            self.assertTrue(event_id.startswith("baseten-"))
            self.assertEqual("llm.baseten.delta", payload["kind"])
            self.assertEqual("baseten", payload["source"]["provider"])
            self.assertTrue(payload["source"]["uri"].endswith("/chat/completions"))

    def test_continuous_openai_runner_creates_job_and_runs_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "openai-loop-unit")
            config = OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="unknown blue device")
            runner = ContinuousOpenAIJobRunner(
                store=store,
                config=config,
                sleep_seconds=0,
                streamer_factory=FakeStreamer,
            )

            reports = []
            runner.run(max_jobs=1, on_job=reports.append)

            self.assertEqual(1, len(reports))
            self.assertTrue(reports[0].passed)
            self.assertEqual(2, reports[0].event_count)
            self.assertTrue(store.agent_path("reader").exists())
            self.assertTrue(store.agent_path("reviewer").exists())
            self.assertTrue(store.agent_path("prompt-iterator").exists())
            self.assertIn("placeholder_text", store.agent_path("reviewer").read_text(encoding="utf-8"))

    def test_continuous_openai_runner_records_request_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "openai-fail-unit")
            config = OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="blue device")
            runner = ContinuousOpenAIJobRunner(
                store=store,
                config=config,
                sleep_seconds=0,
                streamer_factory=FailingStreamer,
            )

            report = runner.run_job(job_index=1)
            event_payload = json.loads(store.events_path.read_text(encoding="utf-8").strip())

            self.assertFalse(report.passed)
            self.assertEqual("llm.openai.failed", event_payload["kind"])
            self.assertIn("unit failure", event_payload["metadata"]["error_message"])
            self.assertTrue(store.agent_path("reviewer").exists())

    def test_queue_runner_processes_job_and_enqueues_iteration_child(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "openai-queue-unit")
            queue = ContinuousOpenAIJobQueue(store)
            config = OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback prompt")
            queued = ContinuousOpenAIJobSpec.create(prompt="unknown blue device", model="gpt-test")
            queue.append_job(queued)
            runner = ContinuousOpenAIJobRunner(
                store=store,
                config=config,
                sleep_seconds=0,
                streamer_factory=FakeStreamer,
            )

            reports = []
            runner.run_queue(max_jobs=1, on_job=reports.append)

            jobs = queue.jobs()
            results = queue.results()
            self.assertEqual(1, len(reports))
            self.assertEqual(2, len(jobs))
            self.assertEqual(1, len(results))
            self.assertEqual(queued.job_id, results[0].job_id)
            self.assertEqual(jobs[1].job_id, results[0].child_job_id)
            self.assertEqual(queued.job_id, jobs[1].parent_job_id)
            self.assertEqual("prompt-iterator", jobs[1].created_by)

    def test_queue_runner_can_clone_successful_job_on_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlStreamStore(Path(temp_dir), "openai-clone-unit")
            queue = ContinuousOpenAIJobQueue(store)
            config = OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback prompt")
            queued = ContinuousOpenAIJobSpec.create(prompt="blue device", model="gpt-test")
            queue.append_job(queued)
            runner = ContinuousOpenAIJobRunner(
                store=store,
                config=config,
                sleep_seconds=0,
                streamer_factory=FakeStreamer,
            )

            runner.run_queue(max_jobs=1, clone_on_pass=True)

            jobs = queue.jobs()
            results = queue.results()
            self.assertEqual(2, len(jobs))
            self.assertEqual(1, len(results))
            self.assertEqual(queued.job_id, jobs[1].parent_job_id)
            self.assertEqual(queued.job_id, jobs[1].clone_of_job_id)
            self.assertEqual("clone-agent", jobs[1].created_by)

    def test_queue_runner_dispatches_baseten_jobs_to_chat_completions(self) -> None:
        FakeChatStreamer.configs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env_file = root / ".env"
            env_file.write_text(
                "BASETEN_API_KEY=test-baseten-key\n"
                "BASETEN_BASE_URL=https://inference.baseten.co/v1\n",
                encoding="utf-8",
            )
            store = JsonlStreamStore(root, "baseten-queue-unit")
            config = OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback prompt")
            queued = ContinuousOpenAIJobSpec.create(
                provider="baseten",
                prompt="review the blue device",
                model="baseten/zai-org/GLM-5.2",
            )
            runner = ContinuousOpenAIJobRunner(
                store=store,
                config=config,
                env_file=env_file,
                sleep_seconds=0,
                streamer_factory=FakeStreamer,
                chat_streamer_factory=FakeChatStreamer,
            )

            report = runner.run_job(job_index=1, job=queued)
            payloads = [json.loads(line) for line in store.events_path.read_text(encoding="utf-8").splitlines()]

            self.assertTrue(report.passed)
            self.assertEqual("baseten", report.provider)
            self.assertEqual("zai-org/GLM-5.2", report.model)
            self.assertEqual("zai-org/GLM-5.2", FakeChatStreamer.configs[0].model)
            self.assertEqual("llm.baseten.delta", payloads[0]["kind"])
            self.assertEqual("baseten", payloads[0]["source"]["provider"])

    def test_queue_runner_dispatches_gmi_jobs_to_chat_completions(self) -> None:
        FakeChatStreamer.configs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env_file = root / ".env"
            env_file.write_text(
                "GMI_API_KEY=test-gmi-key\n"
                "GMI_BASE_URL=https://api.gmi-serving.com/v1\n",
                encoding="utf-8",
            )
            store = JsonlStreamStore(root, "gmi-queue-unit")
            config = OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback prompt")
            queued = ContinuousOpenAIJobSpec.create(
                provider="gemicloud",
                prompt="review the blue device",
                model="gemicloud/fable",
            )
            runner = ContinuousOpenAIJobRunner(
                store=store,
                config=config,
                env_file=env_file,
                sleep_seconds=0,
                streamer_factory=FakeStreamer,
                chat_streamer_factory=FakeChatStreamer,
            )

            report = runner.run_job(job_index=1, job=queued)
            payloads = [json.loads(line) for line in store.events_path.read_text(encoding="utf-8").splitlines()]

            self.assertTrue(report.passed)
            self.assertEqual("gmi", report.provider)
            self.assertEqual("anthropic/claude-fable-5", report.model)
            self.assertEqual("anthropic/claude-fable-5", FakeChatStreamer.configs[0].model)
            self.assertEqual("llm.gmi.delta", payloads[0]["kind"])
            self.assertEqual("gmi", payloads[0]["source"]["provider"])


if __name__ == "__main__":
    unittest.main()
