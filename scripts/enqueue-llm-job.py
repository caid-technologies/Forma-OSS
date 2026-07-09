#!/usr/bin/env python3
"""Provider-neutral entrypoint for appending a continuous LLM job."""

from __future__ import annotations

import runpy
from pathlib import Path


TARGET = Path(__file__).with_name("enqueue-openai-job.py")
runpy.run_path(str(TARGET), run_name="__main__")
