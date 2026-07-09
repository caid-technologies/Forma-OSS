#!/usr/bin/env python3
"""Run configured LLM provider smoke tests and save a JSON report."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT_DIR / "scripts" / "verify-llm-providers.py"
DEFAULT_TIMEOUT_SECONDS = "1200"


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def has_option(args: list[str], *names: str) -> bool:
    for arg in args:
        for name in names:
            if arg == name or arg.startswith(f"{name}="):
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = [str(VERIFY_SCRIPT), "--save"]

    llm_selectors = os.getenv("LLM_SMOKE_LLM")
    if llm_selectors and not has_option(args, "--llm", "--provider"):
        for selector in llm_selectors.split(","):
            selector = selector.strip()
            if selector:
                cmd.extend(["--llm", selector])

    output_dir = os.getenv("LLM_SMOKE_OUTPUT_DIR")
    if output_dir and not has_option(args, "--output-dir", "--output-file"):
        cmd.extend(["--output-dir", output_dir])

    if truthy(os.getenv("LLM_SMOKE_CONFIG_ONLY")) and not has_option(args, "--config-only"):
        cmd.append("--config-only")

    if not has_option(args, "--timeout-seconds"):
        cmd.extend(["--timeout-seconds", os.getenv("LLM_SMOKE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)])

    cmd.extend(args)
    return subprocess.call(cmd, cwd=ROOT_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
