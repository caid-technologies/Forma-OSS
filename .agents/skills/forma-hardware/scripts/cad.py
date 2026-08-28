#!/usr/bin/env python3
"""Managed OpenCAD adapter for the Forma hardware skill.

The skill owns this boundary so callers do not need to know how OpenCAD selects
its native geometry backend or exports an exchange file. OpenCAD is imported
only after the dependency check succeeds.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import runpy
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_OPENCAD_VERSION = "0.2.3"
DEFAULT_OPENCAD_REQUIREMENT = f"opencad[occt]=={SUPPORTED_OPENCAD_VERSION}"
OPENCAD_REQUIREMENT_ENV = "FORMA_OPENCAD_REQUIREMENT"
SUPPORTED_OUTPUT_SUFFIXES = {".step", ".stp", ".stl"}


class OpenCADError(RuntimeError):
    """Raised when the Forma CAD runtime cannot be prepared or used."""


@dataclass(frozen=True)
class OpenCADRuntime:
    """Validated OpenCAD runtime exposed by the Forma adapter."""

    version: str
    requirement: str

    def build_model(self, model: Path, output: Path, tree_output: Path | None) -> int:
        """Run a model with OCCT and export its final shape."""
        try:
            from opencad.kernel.core.backend_factory import create_backend
            from opencad.kernel_adapter import registry_result_to_dict
            from opencad.runtime import RuntimeContext, set_default_context
        except ImportError as exc:
            raise OpenCADError(_diagnostic("the OpenCAD export API could not be imported", self.requirement)) from exc

        try:
            context = RuntimeContext(backend=create_backend("occt", require_native=True))
        except Exception as exc:
            raise OpenCADError(_diagnostic(f"the OCCT backend is unavailable: {exc}", self.requirement)) from exc

        set_default_context(context)
        model_directory = str(model.parent)
        added_model_directory = model_directory not in sys.path
        if added_model_directory:
            sys.path.insert(0, model_directory)
        try:
            runpy.run_path(str(model), run_name="__main__")
        finally:
            if added_model_directory:
                sys.path.remove(model_directory)

        if not context.last_shape_id:
            raise OpenCADError("The OpenCAD model produced no shape to export.")

        operation = "export_stl" if output.suffix.lower() == ".stl" else "export_step"
        result = registry_result_to_dict(
            context.registry,
            operation,
            {"shape_id": context.last_shape_id, "filepath": str(output)},
        )
        if not result.get("ok"):
            raise OpenCADError(f"CAD export failed: {result.get('message', 'unknown error')}")
        if tree_output is not None:
            context.save_tree_json(str(tree_output))
        return len(context.tree.nodes) - 1


def _configured_requirement(requirement: str | None) -> str:
    value = (requirement or os.environ.get(OPENCAD_REQUIREMENT_ENV) or DEFAULT_OPENCAD_REQUIREMENT).strip()
    if not value:
        value = DEFAULT_OPENCAD_REQUIREMENT
    if any(character in value for character in ('"', "\r", "\n")):
        raise OpenCADError(
            f"{OPENCAD_REQUIREMENT_ENV} must be a single pip requirement without quotes or newlines. "
            f"Recovery command: {_recovery_command(DEFAULT_OPENCAD_REQUIREMENT)}"
        )
    return value


def _recovery_command(requirement: str) -> str:
    return f'python -m pip install "{requirement}"'


def _diagnostic(reason: str, requirement: str) -> str:
    return (
        f"OpenCAD {SUPPORTED_OPENCAD_VERSION} with the OCCT extra is unavailable: {reason}.\n"
        f"Recovery command: {_recovery_command(requirement)}"
    )


def _runtime_version(module: Any) -> str | None:
    module_version = str(getattr(module, "__version__", "")).strip()
    if module_version:
        return module_version
    try:
        return importlib.metadata.version("opencad")
    except importlib.metadata.PackageNotFoundError:
        return None


def _inspect_runtime(requirement: str) -> tuple[OpenCADRuntime | None, str]:
    try:
        module = importlib.import_module("opencad")
    except Exception as exc:
        return None, f"the package could not be imported: {exc}"

    runtime_version = _runtime_version(module)
    if runtime_version is None:
        return None, "the installed package does not declare a version"
    if runtime_version != SUPPORTED_OPENCAD_VERSION:
        return None, f"installed version {runtime_version} is incompatible"

    try:
        distribution_version = importlib.metadata.version("opencad")
    except importlib.metadata.PackageNotFoundError:
        distribution_version = None
    if distribution_version is not None and distribution_version != SUPPORTED_OPENCAD_VERSION:
        return None, f"installed distribution version {distribution_version} is incompatible"

    try:
        from opencad.kernel.core.backend_factory import create_backend

        create_backend("occt", require_native=True)
    except Exception as exc:
        return None, f"the native OCCT backend is unavailable: {exc}"

    return OpenCADRuntime(version=runtime_version, requirement=requirement), ""


def _clear_opencad_modules() -> None:
    for name in list(sys.modules):
        if name == "opencad" or name.startswith("opencad."):
            del sys.modules[name]
    importlib.invalidate_caches()


def _install(requirement: str) -> None:
    command = [sys.executable, "-m", "pip", "install", "--upgrade", requirement]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise OpenCADError(_diagnostic(f"pip could not be started: {exc}", requirement)) from exc
    if completed.returncode == 0:
        return

    detail = (completed.stderr or completed.stdout or "pip returned a non-zero exit code").strip()
    if len(detail) > 1200:
        detail = detail[-1200:]
    raise OpenCADError(_diagnostic(f"managed installation failed: {detail}", requirement))


def ensure_opencad(*, install: bool = True, requirement: str | None = None) -> OpenCADRuntime:
    """Return a compatible native runtime, installing the skill dependency if needed."""
    configured = _configured_requirement(requirement)
    runtime, reason = _inspect_runtime(configured)
    if runtime is not None:
        return runtime
    if not install:
        raise OpenCADError(_diagnostic(reason, configured))

    _install(configured)
    _clear_opencad_modules()
    runtime, reason = _inspect_runtime(configured)
    if runtime is None:
        raise OpenCADError(_diagnostic(f"managed installation completed but verification failed: {reason}", configured))
    return runtime


def _temporary_path(destination: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-",
        suffix=destination.suffix,
        dir=destination.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _binary_stl_triangle_count(data: bytes) -> int | None:
    if len(data) < 84:
        return None
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    return triangle_count if 84 + triangle_count * 50 == len(data) else None


def inspect_cad_file(filepath: str | Path) -> dict[str, Any]:
    """Validate the basic exchange-file structure before publishing an output."""
    path = Path(filepath)
    if not path.is_file():
        raise OpenCADError(f"CAD file does not exist: {path}")
    data = path.read_bytes()
    if not data:
        raise OpenCADError(f"CAD file is empty: {path}")

    suffix = path.suffix.lower()
    if suffix in {".step", ".stp"}:
        upper = data.upper()
        if not upper.lstrip().startswith(b"ISO-10303-21;"):
            raise OpenCADError("STEP validation failed: missing ISO-10303-21 header.")
        if b"END-ISO-10303-21;" not in upper or b"DATA;" not in upper or b"ENDSEC;" not in upper:
            raise OpenCADError("STEP validation failed: missing exchange data section or end marker.")
        return {"format": "step", "path": str(path.resolve()), "bytes": len(data), "valid": True}

    if suffix == ".stl":
        triangle_count = _binary_stl_triangle_count(data)
        encoding = "binary"
        if triangle_count is None:
            text = data.decode("utf-8", errors="replace").lower()
            if not text.lstrip().startswith("solid") or "endsolid" not in text:
                raise OpenCADError("STL validation failed: file is neither valid binary nor recognizable ASCII STL.")
            triangle_count = text.count("facet normal")
            encoding = "ascii"
        if triangle_count < 1:
            raise OpenCADError("STL validation failed: mesh contains no triangles.")
        return {
            "format": "stl",
            "encoding": encoding,
            "triangles": triangle_count,
            "path": str(path.resolve()),
            "bytes": len(data),
            "valid": True,
        }

    raise OpenCADError("Unsupported CAD format. Use a .step, .stp, or .stl file.")


def build_cad_file(
    model: str | Path,
    output: str | Path,
    *,
    tree_output: str | Path | None = None,
    force: bool = False,
    requirement: str | None = None,
) -> dict[str, Any]:
    """Build, validate, and atomically publish a CAD artifact."""
    model_path = Path(model).resolve()
    output_path = Path(output).resolve()
    tree_path = Path(tree_output).resolve() if tree_output else None
    if not model_path.is_file():
        raise OpenCADError(f"Model script does not exist: {model_path}")
    if model_path.suffix.lower() != ".py":
        raise OpenCADError("The OpenCAD model must be a .py file.")
    if output_path.suffix.lower() not in SUPPORTED_OUTPUT_SUFFIXES:
        raise OpenCADError("Output must end in .step, .stp, or .stl.")
    if tree_path == output_path:
        raise OpenCADError("CAD output and feature-tree output must use different paths.")
    for destination in (output_path, tree_path):
        if destination is not None and destination.exists() and not force:
            raise OpenCADError(f"Refusing to replace existing file without --force: {destination}")

    runtime = ensure_opencad(requirement=requirement)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if tree_path is not None:
        tree_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = _temporary_path(output_path)
    temporary_tree = _temporary_path(tree_path) if tree_path is not None else None

    try:
        feature_count = runtime.build_model(model_path, temporary_output, temporary_tree)
        summary = inspect_cad_file(temporary_output)
        summary["features"] = feature_count
        os.replace(temporary_output, output_path)
        summary["path"] = str(output_path)
        if tree_path is not None and temporary_tree is not None:
            os.replace(temporary_tree, tree_path)
            summary["tree_path"] = str(tree_path)
        summary["model_path"] = str(model_path)
        summary["opencad_version"] = runtime.version
        return summary
    finally:
        temporary_output.unlink(missing_ok=True)
        if temporary_tree is not None:
            temporary_tree.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare OpenCAD and build Forma CAD artifacts.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("setup", "Install and verify the managed OpenCAD runtime."),
        ("check", "Verify OpenCAD without installing anything."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--requirement", help=f"Optional pip requirement override (also {OPENCAD_REQUIREMENT_ENV}).")

    build = commands.add_parser("build", help="Build and validate a STEP or STL artifact from an OpenCAD model.")
    build.add_argument("model", help="OpenCAD Python model")
    build.add_argument("output", help="Destination ending in .step, .stp, or .stl")
    build.add_argument("--tree-output", help="Optional feature-tree JSON destination")
    build.add_argument("--force", action="store_true", help="Replace existing output files")
    build.add_argument("--requirement", help=f"Optional pip requirement override (also {OPENCAD_REQUIREMENT_ENV}).")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"setup", "check"}:
        runtime = ensure_opencad(install=args.command == "setup", requirement=args.requirement)
        return {
            "opencad_version": runtime.version,
            "requirement": runtime.requirement,
            "occt": True,
            "valid": True,
        }
    return build_cad_file(
        args.model,
        args.output,
        tree_output=args.tree_output,
        force=args.force,
        requirement=args.requirement,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True))
        return 0
    except (OpenCADError, OSError, ValueError) as exc:
        print(f"forma-cad: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
