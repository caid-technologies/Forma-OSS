#!/usr/bin/env python3
"""Validate Forma production environment variables without printing secrets."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
TRUTHY = {"1", "true", "yes", "on"}
AUTH_ALLOWLIST_KEYS = (
    "BLUEPRINT_ADMIN_USER_IDS",
    "CLERK_ADMIN_USER_IDS",
    "BLUEPRINT_ADMIN_EMAILS",
    "CLERK_ADMIN_EMAILS",
)
PROVIDER_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "LLM_API_KEY"),
    "openai": ("OPENAI_API_KEY", "LLM_API_KEY"),
    "baseten": ("BASETEN_API_KEY", "LLM_API_KEY"),
    "gmi": ("GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY", "LLM_API_KEY"),
    "huggingface": ("HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN", "HF_API_TOKEN", "LLM_API_KEY"),
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NIM_API_KEY", "LLM_API_KEY"),
    "runpod": ("RUNPOD_API_KEY", "LLM_API_KEY"),
    "runpod-serverless": ("RUNPOD_API_KEY",),
    "openai-compatible": ("LLM_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"),
    "simulation": (),
}


class CheckReport:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []
        self.warnings: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.results.append((label, ok, detail))

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def print(self) -> None:
        for label, ok, detail in self.results:
            status = "PASS" if ok else "FAIL"
            suffix = f" ({detail})" if detail else ""
            print(f"{status}\t{label}{suffix}")
        for warning in self.warnings:
            print(f"WARN\t{warning}")
        passed = sum(1 for _, ok, _ in self.results if ok)
        print(f"SUMMARY\t{passed}/{len(self.results)} checks passed")
        failed = [label for label, ok, _ in self.results if not ok]
        if failed:
            print("FAILED\t" + ", ".join(failed))

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.results)


def normalize_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    value = value.replace("\\n", "\n").strip()
    return value


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        env[key] = normalize_value(value)
    return env


def pull_vercel_env(environment: str) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    temp_dir = tempfile.TemporaryDirectory(prefix="blueprint-production-env-")
    env_path = Path(temp_dir.name) / ".env"
    command = ["vercel", "env", "pull", str(env_path), "--environment", environment, "--yes"]
    subprocess.run(command, cwd=ROOT_DIR, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    return env_path, temp_dir


def first_present(env: dict[str, str], names: Iterable[str]) -> str | None:
    for name in names:
        if env.get(name, "").strip():
            return name
    return None


def is_true(env: dict[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in TRUTHY


def key_mode(value: str) -> str | None:
    if value.startswith(("pk_live_", "sk_live_")):
        return "live"
    if value.startswith(("pk_test_", "sk_test_")):
        return "test"
    return None


def validate(env: dict[str, str], *, require_live_clerk: bool) -> CheckReport:
    report = CheckReport()
    value = lambda name: env.get(name, "").strip()

    report.check("Supabase URL present", bool(value("SUPABASE_URL")))
    report.check("Supabase service/secret key present", bool(first_present(env, ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"))))
    report.check("Database backend is Supabase", value("DATABASE_BACKEND").lower() == "supabase", f"DATABASE_BACKEND={value('DATABASE_BACKEND') or '<unset>'}")
    report.check("Job metadata not forced to SQLite", value("JOB_METADATA_BACKEND").lower() != "sqlite", f"JOB_METADATA_BACKEND={value('JOB_METADATA_BACKEND') or '<unset>'}")
    report.check("Forma dev mode disabled", not is_true(env, "BLUEPRINT_DEV_MODE"))
    report.check("Frontend dev mode disabled", not is_true(env, "NEXT_PUBLIC_BLUEPRINT_DEV_MODE"))
    report.check("Backend debug disabled", not is_true(env, "BLUEPRINT_DEBUG"))
    report.check("Frontend debug disabled", not is_true(env, "NEXT_PUBLIC_BLUEPRINT_DEBUG"))

    publishable_key_name = first_present(env, ("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "CLERK_PUBLISHABLE_KEY"))
    secret_key_name = first_present(env, ("CLERK_SECRET_KEY",))
    report.check("Clerk publishable key present", bool(publishable_key_name))
    report.check("Clerk secret key present", bool(secret_key_name))
    report.check("Admin allowlist present", bool(first_present(env, AUTH_ALLOWLIST_KEYS)), "or use Clerk JWT admin metadata")
    report.check("Auth required not explicitly disabled", value("BLUEPRINT_AUTH_REQUIRED").lower() not in {"0", "false", "no", "off"})

    if publishable_key_name:
        mode = key_mode(value(publishable_key_name))
        if mode == "test":
            message = f"{publishable_key_name} is a Clerk test key"
            if require_live_clerk:
                report.check("Clerk publishable key is live", False, message)
            else:
                report.warn(message)
    if secret_key_name:
        mode = key_mode(value(secret_key_name))
        if mode == "test":
            message = f"{secret_key_name} is a Clerk test key"
            if require_live_clerk:
                report.check("Clerk secret key is live", False, message)
            else:
                report.warn(message)

    provider = value("LLM_PROVIDER").lower()
    report.check("LLM provider selected", bool(provider))
    if provider == "simulation":
        report.check("Production not using simulation provider", False, "LLM_PROVIDER=simulation")
    elif provider in PROVIDER_KEYS:
        report.check(f"{provider} provider key present", bool(first_present(env, PROVIDER_KEYS[provider])))
    else:
        report.check("Recognized LLM provider", False, f"LLM_PROVIDER={provider or '<unset>'}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", default="production", help="Vercel environment to pull when --env-file is omitted.")
    parser.add_argument("--env-file", type=Path, default=None, help="Validate an existing dotenv file instead of pulling from Vercel.")
    parser.add_argument("--require-live-clerk", action="store_true", help="Fail if Clerk keys are test-mode keys.")
    args = parser.parse_args()

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if args.env_file:
            env_path = args.env_file.expanduser()
        else:
            env_path, temp_dir = pull_vercel_env(args.environment)
        env = parse_env_file(env_path)
        report = validate(env, require_live_clerk=args.require_live_clerk)
        report.print()
        return 0 if report.ok else 1
    except FileNotFoundError as exc:
        print(f"ERROR\tRequired command or file not found: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or str(exc)).strip()
        print(f"ERROR\tFailed to pull Vercel env: {message}", file=sys.stderr)
        return 2
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
