from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT_DIR = Path(__file__).resolve().parents[2]
DEV_PROCESSES = ROOT_DIR / "scripts" / "development" / "dev-processes.sh"


def run_bash(script: str, root: Path) -> subprocess.CompletedProcess[str]:
    inherited_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {
            "DATABASE_BACKEND",
            "FORMA_AUTH_MODE",
            "FORMA_DEV_MODE",
            "FORMA_USER_SECRETS_KEY",
            "IMAGE_OUTPUT_ENABLED",
            "IMAGE_PROVIDER",
            "LLM_PROVIDER",
            "NEXT_PUBLIC_API_URL",
            "NEXT_PUBLIC_FORMA_DEV_MODE",
            "SQLITE_DATABASE_URL",
        }
    }
    env = {
        **inherited_env,
        "ROOT_DIR": str(root),
        "PYTHON_BIN": sys.executable,
        "BACKEND_HOST": "127.0.0.1",
        "BACKEND_PORT": "8123",
        "FRONTEND_HOST": "127.0.0.1",
        "FRONTEND_PORT": "3123",
    }
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


class DevelopmentScriptTests(unittest.TestCase):
    def test_zero_config_defaults_to_local_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_bash(
                textwrap.dedent(
                    f"""
                    set -euo pipefail
                    source {shlex.quote(str(DEV_PROCESSES))}
                    dev_ensure_local_simulation_env
                    test -s "$DEV_RUNTIME_DIR/forma-user-secrets.key"
                    printf '%s\\n' "$FORMA_AUTH_MODE|$FORMA_DEV_MODE|$DATABASE_BACKEND|$LLM_PROVIDER|$IMAGE_PROVIDER|$NEXT_PUBLIC_FORMA_DEV_MODE"
                    printf '%s\\n' "$SQLITE_DATABASE_URL"
                    """
                ),
                root,
            )

        lines = result.stdout.strip().splitlines()
        self.assertEqual("local|true|sqlite|simulation|none|true", lines[0])
        self.assertIn("/tmp/development/forma-dev.db", lines[1])

    def test_existing_env_file_keeps_environment_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("FORMA_AUTH_MODE=local\n", encoding="utf-8")
            result = run_bash(
                textwrap.dedent(
                    f"""
                    set -euo pipefail
                    source {shlex.quote(str(DEV_PROCESSES))}
                    dev_ensure_local_simulation_env
                    test ! -e "$DEV_RUNTIME_DIR/forma-user-secrets.key"
                    printf '%s\\n' "${{FORMA_USER_SECRETS_KEY-unset}}|${{LLM_PROVIDER-unset}}"
                    """
                ),
                root,
            )

        self.assertEqual("unset|unset", result.stdout.strip())

    def test_explicit_sqlite_url_parent_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_bash(
                textwrap.dedent(
                    f"""
                    set -euo pipefail
                    export FORMA_USER_SECRETS_KEY=explicit-test-secret
                    export SQLITE_DATABASE_URL="sqlite:///$ROOT_DIR/custom/db/forma.db"
                    source {shlex.quote(str(DEV_PROCESSES))}
                    dev_ensure_local_simulation_env
                    test -d "$ROOT_DIR/custom/db"
                    printf 'created\\n'
                    """
                ),
                root,
            )

        self.assertEqual("created", result.stdout.strip())

    def test_process_group_lifecycle_uses_recorded_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_bash(
                textwrap.dedent(
                    f"""
                    set -euo pipefail
                    source {shlex.quote(str(DEV_PROCESSES))}
                    mkdir -p "$DEV_RUNTIME_DIR"
                    dev_start_process_group child "$DEV_RUNTIME_DIR/test.pgid" "$DEV_RUNTIME_DIR/test.log" "$PYTHON_BIN" -c 'import time; time.sleep(30)'
                    read -r recorded_pid recorded_root <"$DEV_RUNTIME_DIR/test.pgid"
                    test "$recorded_pid" = "$child"
                    test "$recorded_root" = "$ROOT_DIR"
                    dev_group_is_running "$child"
                    dev_stop_process_group "$child" "test" "$DEV_RUNTIME_DIR/test.pgid" "$recorded_root"
                    test ! -e "$DEV_RUNTIME_DIR/test.pgid"
                    if dev_group_is_running "$child"; then exit 7; fi
                    printf 'stopped\\n'
                    """
                ),
                root,
            )

        self.assertEqual("stopped", result.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
