#!/usr/bin/env python3
"""Render local images directly in the terminal with ANSI color blocks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.terminal_images import TerminalImageRenderConfig, render_images


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="+", type=Path)
    parser.add_argument("--width", type=int, default=None, help="Maximum terminal columns to use.")
    parser.add_argument("--max-height", type=int, default=40, help="Maximum terminal rows to use per image.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    config = TerminalImageRenderConfig(width=args.width, max_height=args.max_height)
    print(render_images([path.expanduser() for path in args.image], config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
