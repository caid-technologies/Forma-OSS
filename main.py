"""Vercel fallback ASGI entrypoint.

The preferred entrypoint is configured as ``apps.api.main:app``. This shim keeps
older Vercel auto-detection paths from flattening ``apps/api/main.py`` into a
top-level ``main.py`` without the monorepo packages beside it.
"""

from apps.api.main import app

application = app
