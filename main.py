"""Vercel fallback ASGI entrypoint.

The preferred entrypoint is configured as ``backend.main:app``. This shim keeps
older Vercel auto-detection paths from flattening ``backend/main.py`` into a
top-level ``main.py`` without the monorepo packages beside it.
"""

from backend.main import app

application = app
