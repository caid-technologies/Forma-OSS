from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blueprint_core.logs import backend_log_payload, redact_log_line, resolve_backend_log_path


class BackendLogCoreTests(unittest.TestCase):
    def test_resolve_backend_log_path_uses_env_and_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = resolve_backend_log_path(env={"BACKEND_LOG_FILE": "logs/backend.log"}, cwd=Path(tmp_dir))

        self.assertEqual(Path(tmp_dir, "logs/backend.log").resolve(), path)

    def test_resolve_backend_log_path_returns_none_when_unset(self) -> None:
        self.assertIsNone(resolve_backend_log_path(env={}))

    def test_redact_log_line_hides_provider_keys(self) -> None:
        line = "openai=sk-testsecret123456 firecrawl=fc-abcdefghijklmnop visible=ok"

        redacted = redact_log_line(line)

        self.assertNotIn("sk-testsecret123456", redacted)
        self.assertNotIn("fc-abcdefghijklmnop", redacted)
        self.assertIn("visible=ok", redacted)

    def test_backend_log_payload_reports_missing_configuration(self) -> None:
        payload = backend_log_payload(env={})

        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["configured"])
        self.assertEqual("BACKEND_LOG_FILE is not configured.", payload["message"])

    def test_backend_log_payload_reports_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_path = Path(tmp_dir) / "missing.log"
            payload = backend_log_payload(log_path=missing_path)

        self.assertFalse(payload["enabled"])
        self.assertTrue(payload["configured"])
        self.assertEqual(str(missing_path), payload["path"])
        self.assertEqual("Backend log file does not exist yet.", payload["message"])

    def test_backend_log_payload_tails_and_redacts_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "backend.log"
            log_path.write_text(
                "\n".join(
                    [
                        "first line",
                        "secret sk-testsecret123456",
                        "last line",
                    ]
                ),
                encoding="utf-8",
            )

            payload = backend_log_payload(log_path=log_path, line_limit=2, byte_limit=500_000)

        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["truncated"])
        self.assertEqual(2, payload["line_count"])
        self.assertEqual(["secret <redacted>", "last line"], payload["lines"])


if __name__ == "__main__":
    unittest.main()
