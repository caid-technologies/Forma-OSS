#!/usr/bin/env python3
"""Install the portable Forma Agent Skill for Claude Code and/or Codex."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


SKILL_NAME = "forma-hardware"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO_ROOT / "integrations" / "agent-skills" / SKILL_NAME
AGENT_PATHS = {
    "claude": Path(".claude") / "skills" / SKILL_NAME,
    "codex": Path(".agents") / "skills" / SKILL_NAME,
}


def install_skill(source: Path, destination: Path, *, force: bool = False) -> Path:
    if not (source / "SKILL.md").is_file():
        raise ValueError(f"Forma skill source is invalid: {source}")
    if destination.exists() and not force:
        raise FileExistsError(f"Skill already exists at {destination}; pass --force to update it.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=force)
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("claude", "codex", "both"), default="both")
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="Update an existing installed skill.")
    parser.add_argument("--dry-run", action="store_true", help="Print destinations without copying files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agents = tuple(AGENT_PATHS) if args.agent == "both" else (args.agent,)
    base = args.home.expanduser() if args.scope == "user" else args.project_dir.expanduser().resolve()

    try:
        for agent in agents:
            destination = base / AGENT_PATHS[agent]
            if not args.dry_run:
                install_skill(args.source.resolve(), destination, force=args.force)
            print(f"{agent}: {destination}")
    except (OSError, ValueError) as exc:
        print(f"install-forma-skill: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
