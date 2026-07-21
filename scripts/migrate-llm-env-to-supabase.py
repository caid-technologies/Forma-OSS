#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.production.local", override=False)
load_dotenv(ROOT / ".env.local", override=False)

from blueprint_core.user_integrations import (  # noqa: E402
    INTEGRATION_DEFINITIONS,
    SupabaseWorkspaceIntegrationStore,
    UserIntegrationConfig,
)


MIGRATED_INTEGRATION_IDS = {
    "runtime",
    "image",
    "openai",
    "anthropic",
    "baseten",
    "runpod",
    "gmi",
    "huggingface",
    "nvidia",
    "gemini",
    "ollama",
}


def first_env(env_names: tuple[str, ...]) -> str | None:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate provider/image env defaults into encrypted Supabase workspace settings.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Overwrite the workspace config from env without decrypting the existing row. Use only when rotating workspace defaults/encryption.",
    )
    args = parser.parse_args()

    store = SupabaseWorkspaceIntegrationStore()
    config = UserIntegrationConfig() if args.reset else store.load()
    changed = 0

    for definition in INTEGRATION_DEFINITIONS:
        if definition.id not in MIGRATED_INTEGRATION_IDS:
            continue

        fields: dict[str, str] = {}
        for field in definition.fields:
            value = first_env(field.env_names)
            if value:
                fields[field.id] = value

        if not fields:
            continue

        integration = config.ensure_integration(definition.id)
        integration.enabled = True
        for field_id, value in fields.items():
            definition.field_by_id(field_id)
            integration.set_field(field_id, value)
        changed += 1
        print(f"migrated {definition.id}: {', '.join(sorted(fields))}")

    if changed == 0:
        print("No LLM/provider env values found to migrate.")
        return 0

    store.save(config)
    print(f"Migrated {changed} LLM/image integrations into encrypted Supabase workspace config.")
    print("Set BLUEPRINT_WORKSPACE_INTEGRATIONS_BACKEND=supabase on the backend to use it at runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
