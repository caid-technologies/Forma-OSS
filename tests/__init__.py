"""Test-safe environment defaults.

The application modules load `.env` at import time. These defaults keep normal
unit tests offline and on SQLite even when a developer has live provider keys in
their local environment.
"""

import os


os.environ.setdefault("BLUEPRINT_DEV_MODE", "true")
os.environ.setdefault("DATABASE_BACKEND", "sqlite")
os.environ.setdefault("SQLITE_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JOB_METADATA_BACKEND", "sqlite")
os.environ.setdefault("LLM_PROVIDER", "simulation")
os.environ.setdefault("IMAGE_PROVIDER", "none")
os.environ.setdefault("IMAGE_OUTPUT_ENABLED", "false")
