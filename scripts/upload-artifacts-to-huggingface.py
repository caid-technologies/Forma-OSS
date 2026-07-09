#!/usr/bin/env python3
"""Upload Blueprint output, benchmark, or eval artifacts to a Hugging Face dataset repo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from blueprint_core.huggingface_artifacts import (
    HuggingFaceUploadConfig,
    build_artifacts,
    path_from_repo,
    upload_artifacts_to_huggingface,
)


DEFAULT_GLOBS = {
    "outputs": ("examples/results/*.json", ".logs/provider-image-jobs/*", ".logs/image-jobs/*"),
    "benchmarks": (".logs/benchmarks/*.json", ".logs/benchmarks/*.jsonl", ".logs/benchmarks/*.csv"),
    "evals": (".logs/evals/*.json", ".logs/evals/*.jsonl", ".logs/evals/*.csv"),
}


def expand_inputs(paths: list[str], globs: list[str], *, artifact_type: str) -> list[Path]:
    expanded: list[Path] = []
    raw_inputs = [*paths, *globs]
    if not raw_inputs:
        raw_inputs = list(DEFAULT_GLOBS.get(artifact_type, ()))

    for raw_value in raw_inputs:
        if any(char in raw_value for char in "*?["):
            expanded.extend(path for path in ROOT_DIR.glob(raw_value) if path.is_file())
        else:
            path = path_from_repo(raw_value, root_dir=ROOT_DIR)
            if path.is_dir():
                expanded.extend(item for item in path.rglob("*") if item.is_file())
            elif path.is_file():
                expanded.append(path)
    return sorted(dict.fromkeys(expanded))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload Blueprint artifacts to Hugging Face.")
    parser.add_argument("paths", nargs="*", help="Files or directories to upload. Defaults depend on --artifact-type.")
    parser.add_argument("--glob", action="append", default=[], help="Glob relative to the repo root. Can be repeated.")
    parser.add_argument(
        "--artifact-type",
        choices=("outputs", "benchmarks", "evals"),
        default="benchmarks",
        help="Artifact family. Controls default globs and destination path.",
    )
    parser.add_argument("--hf-repo-id", help="Hugging Face dataset repo id, for example username/blueprint-metrics. Defaults to HF_ARTIFACT_REPO_ID.")
    parser.add_argument("--hf-repo-type", default="dataset", help="Hugging Face repo type. Defaults to dataset.")
    parser.add_argument("--hf-path-prefix", default="blueprint", help="Path prefix inside the Hugging Face repo. Defaults to blueprint.")
    parser.add_argument("--hf-private", action="store_true", help="Create the Hugging Face repo as private when it does not exist.")
    parser.add_argument("--hf-no-create-repo", action="store_true", help="Do not create the Hugging Face repo before uploading.")
    parser.add_argument("--hf-commit-message", default="Upload Blueprint artifacts", help="Commit message for Hugging Face uploads.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable upload metadata.")
    parser.add_argument("--dry-run", action="store_true", help="List artifacts without uploading.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = expand_inputs(args.paths, args.glob, artifact_type=args.artifact_type)

    if not paths:
        print("[hf-artifacts] no artifacts found", file=sys.stderr)
        return 2

    if args.dry_run:
        artifacts = build_artifacts(
            paths,
            artifact_type=args.artifact_type,
            path_prefix=args.hf_path_prefix,
            root_dir=ROOT_DIR,
        )
        payload: dict[str, Any] = {
            "repo_id": args.hf_repo_id,
            "repo_type": args.hf_repo_type,
            "path_prefix": args.hf_path_prefix,
            "dry_run": True,
            "count": len(artifacts),
            "artifacts": [artifact.as_manifest_item() for artifact in artifacts],
        }
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(str(item.local_path) for item in artifacts))
        return 0

    config = HuggingFaceUploadConfig.from_env(
        repo_id=args.hf_repo_id,
        repo_type=args.hf_repo_type,
        private=bool(args.hf_private),
        create_repo=not bool(args.hf_no_create_repo),
        path_prefix=args.hf_path_prefix,
        commit_message=args.hf_commit_message,
    )
    artifacts = build_artifacts(
        paths,
        artifact_type=args.artifact_type,
        path_prefix=config.path_prefix,
        root_dir=ROOT_DIR,
    )

    result = upload_artifacts_to_huggingface(artifacts, config=config)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"[hf-artifacts] repo={result.repo_id} uploaded={result.count}")
        for item in result.uploaded_files:
            print(f"[hf-artifacts] uploaded {item.artifact.local_path} -> {item.artifact.path_in_repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
