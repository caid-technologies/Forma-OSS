#!/usr/bin/env python3
"""Generate a project through the public FormaClient SDK."""

from __future__ import annotations

import sys
from pathlib import Path

# Permit ``python examples/forma_core/intent.py`` from a source checkout.
if __package__ in {None, ""}:
    repository_root = Path(__file__).resolve().parents[2]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from forma_core import FormaClient


def main() -> None:
    client = FormaClient.from_config()
    try:
        run = client.projects.start_generation(
            prompt=(
                "Design a compact desktop environmental monitor using an ESP32, "
                "a temperature and humidity sensor, an OLED, and USB-C power."
            ),
        )

        result = run.wait()

        print(result.status)
        print(result.completeness.valid_bom_line_count)
        print(result.completeness.resolved_obligation_count)

        if result.project is not None:
            print(result.project.model_dump_json(indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
