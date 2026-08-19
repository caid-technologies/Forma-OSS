#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forma_core.config import config  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test local Supabase-backed encrypted workspace integration settings."
    )
    parser.add_argument(
        "--config-key",
        default=f"local-smoke-{uuid.uuid4()}",
        help="Temporary workspace_integration_configs.config_key to use.",
    )
    parser.add_argument(
        "--keep-row",
        action="store_true",
        help="Keep the temporary row instead of deleting it after verification.",
    )
    args = parser.parse_args()

    config.set_default("DATABASE_BACKEND", "supabase")
    config.set_default("FORMA_DEV_MODE", "true")
    config.set_default("FORMA_WORKSPACE_INTEGRATIONS_BACKEND", "supabase")
    config.set_default("FORMA_WORKSPACE_CONFIG_CACHE_TTL_SECONDS", "0")
    config.set_default("FORMA_WORKSPACE_CONFIG_FAILURE_TTL_SECONDS", "0")

    from forma_core.database import get_database_config
    from forma_core.user_integrations import SupabaseWorkspaceIntegrationStore, UserIntegrationConfig

    db_config = get_database_config()
    print(f"database backend: {db_config['backend']} ({db_config['url']}) dev_mode={db_config['dev_mode']}")
    if db_config["backend"] != "supabase":
        raise SystemExit("Expected local Supabase backend. Check DATABASE_BACKEND, FORMA_DEV_MODE, and SUPABASE_URL.")

    store = SupabaseWorkspaceIntegrationStore(config_key=args.config_key)
    config = UserIntegrationConfig()
    runtime = config.ensure_integration("runtime")
    runtime.enabled = True
    runtime.set_field("provider", "huggingface")
    runtime.set_field("model", "local-smoke-model")

    print(f"writing encrypted workspace config: {store.storage_label}")
    store.save(config)

    loaded = store.load()
    loaded_runtime = loaded.integration_by_id("runtime")
    loaded_provider = loaded_runtime.field_value("provider") if loaded_runtime else None
    loaded_model = loaded_runtime.field_value("model") if loaded_runtime else None
    if loaded_provider != "huggingface" or loaded_model != "local-smoke-model":
        raise SystemExit(
            "Supabase workspace integration round trip failed: "
            f"provider={loaded_provider!r} model={loaded_model!r}"
        )

    print("workspace integration round trip: ok")

    if not args.keep_row:
        store._client().table(store.table_name).delete().eq("config_key", args.config_key).execute()
        print(f"deleted temporary config row: {args.config_key}")
    else:
        print(f"kept temporary config row: {args.config_key}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
