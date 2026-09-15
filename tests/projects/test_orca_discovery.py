"""Worker discovery needs no FORMA_ORCA_* variables and ignores user path overrides."""
from pathlib import Path
from unittest.mock import patch

from forma_core.workspaces.projects.fabrication.demo_printers import (
    demo_printer_capabilities, orca_profile_root,
)
from forma_core.workspaces.projects.fabrication.slicers.orca import OrcaSlicerAdapter


def test_worker_path_and_profiles_are_discovered_without_environment_configuration(tmp_path, monkeypatch):
    executable = tmp_path / "OrcaSlicer" / "orca-slicer"
    executable.parent.mkdir()
    executable.write_text("fixture")
    profiles = executable.parent / "resources" / "profiles"
    profiles.mkdir(parents=True)
    # Even an inherited obsolete override cannot redirect this flow to a server executable/profile.
    monkeypatch.setenv("FORMA_ORCA_SLICER_PATH", "/untrusted/binary")
    monkeypatch.setenv("FORMA_ORCA_PROFILE_ROOT", "/untrusted/profiles")
    with patch("forma_core.workspaces.projects.fabrication.slicers.orca.shutil.which", return_value=str(executable)):
        adapter = OrcaSlicerAdapter()
        assert adapter.executable is None
        assert adapter.executable_path() == executable.resolve()
        assert orca_profile_root(adapter) == profiles.resolve()


def test_worker_uses_standard_install_location_when_not_on_path(tmp_path):
    exe = tmp_path / "OrcaSlicer.exe"
    exe.write_text("fixture")
    with patch("forma_core.workspaces.projects.fabrication.slicers.orca.shutil.which", return_value=None), patch.object(
        OrcaSlicerAdapter, "_standard_install_candidates", return_value=[exe]
    ):
        assert OrcaSlicerAdapter().executable_path() == exe.resolve()


def test_missing_slicer_stays_unavailable_without_environment_instructions():
    with patch.object(OrcaSlicerAdapter, "executable_path", return_value=None):
        rows = demo_printer_capabilities()
    assert all(not row["available"] for row in rows)
    assert all("STEP" in row["unavailable_reason"] for row in rows)
    assert "FORMA_ORCA" not in str(rows)


def test_missing_profiles_does_not_expose_worker_filesystem_paths(tmp_path):
    exe = tmp_path / "private-user-data" / "orca-slicer"
    exe.parent.mkdir()
    exe.write_text("fixture")
    with patch.object(OrcaSlicerAdapter, "executable_path", return_value=exe):
        rows = demo_printer_capabilities()
    assert all(not row["available"] for row in rows)
    assert "private-user-data" not in str(rows)
