#!/usr/bin/env python3
"""Provider-neutral entrypoint for the continuous LLM job worker."""

from __future__ import annotations

import runpy
from pathlib import Path


TARGET = Path(__file__).with_name("run-continuous-openai-jobs.py")
runpy.run_path(str(TARGET), run_name="__main__")
