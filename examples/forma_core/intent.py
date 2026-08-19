#!/usr/bin/env python3
"""Generate a project through the public FormaClient SDK."""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Permit ``python examples/forma_core/intent.py`` from a source checkout.
if __package__ in {None, ""}:
    repository_root = Path(__file__).resolve().parents[2]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from forma_core import FormaClient


def main() -> None:
    client = FormaClient.from_config()
    started_at = time.perf_counter()

    try:
        run = client.projects.start_generation(
            prompt=(
                "Design a compact desktop environmental monitor using an ESP32, "
                "a temperature and humidity sensor, an OLED, and USB-C power."
            ),
        )

        result = run.wait()
        elapsed_seconds = time.perf_counter() - started_at

        print(f"Generation time: {elapsed_seconds:.2f} seconds")
        print(f"Generation time: {elapsed_seconds / 60:.2f} minutes")
        print(result.status)
        print(result.completeness.valid_bom_line_count)
        print(result.completeness.resolved_obligation_count)

        if result.project is not None:
            print(result.project.model_dump_json(indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
