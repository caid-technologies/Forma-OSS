from __future__ import annotations

import importlib.metadata
import json
import pathlib
import tomllib
import unittest

import blueprint_core


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
CORE_DIR = ROOT_DIR / "blueprint_core"
DIST_NAME = "caid-blueprint-core"


class CorePackageTests(unittest.TestCase):
    def test_blueprint_core_exports_package_version(self) -> None:
        self.assertRegex(blueprint_core.__version__, r"^\d+\.\d+\.\d+")

    def test_pyproject_declares_installable_typed_core_package(self) -> None:
        pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(DIST_NAME, pyproject["project"]["name"])
        self.assertEqual(["version"], pyproject["project"]["dynamic"])
        self.assertEqual("blueprint_core._version.__version__", pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"])
        self.assertIn("blueprint_core.*", pyproject["tool"]["setuptools"]["packages"]["find"]["include"])
        self.assertIn("py.typed", pyproject["tool"]["setuptools"]["package-data"]["blueprint_core"])
        self.assertTrue((CORE_DIR / "py.typed").exists())

    def test_backend_requirements_pin_published_core_package(self) -> None:
        requirements_path = ROOT_DIR / "backend" / "requirements.txt"
        requirements = requirements_path.read_text(encoding="utf-8").splitlines()
        requirement = next(
            (line.split("#", 1)[0].strip() for line in requirements if line.split("#", 1)[0].strip().startswith(f"{DIST_NAME}==")),
            None,
        )

        self.assertEqual(f"{DIST_NAME}=={blueprint_core.__version__}", requirement)

    def test_vercel_backend_installs_local_core_package(self) -> None:
        vercel_config = json.loads((ROOT_DIR / "vercel.json").read_text(encoding="utf-8"))

        self.assertNotIn("experimentalServices", vercel_config)
        backend = vercel_config["services"]["backend"]
        self.assertEqual(".", backend["root"])
        self.assertEqual("fastapi", backend["framework"])
        self.assertEqual("backend.main:app", backend["entrypoint"])
        self.assertEqual("python -m pip install . -r backend/requirements.txt", backend["installCommand"])
        self.assertIn(
            {"source": "/api/(.*)", "destination": {"service": "backend"}},
            vercel_config["rewrites"],
        )

    def test_installed_distribution_metadata_when_available(self) -> None:
        try:
            version = importlib.metadata.version(DIST_NAME)
        except importlib.metadata.PackageNotFoundError:
            self.skipTest(f"{DIST_NAME} is not installed in this interpreter")

        self.assertEqual(blueprint_core.__version__, version)

    def test_blueprint_core_does_not_import_backend_modules(self) -> None:
        offenders: list[str] = []
        for path in CORE_DIR.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "from backend" in text or "import backend" in text or "backend." in text:
                offenders.append(str(path.relative_to(ROOT_DIR)))

        self.assertEqual([], offenders)

    def test_generation_package_imports(self) -> None:
        from blueprint_core.generation import HardwarePipelineOrchestrator, list_workflows
        from blueprint_core.models import HardwareIR

        self.assertEqual("HardwarePipelineOrchestrator", HardwarePipelineOrchestrator.__name__)
        self.assertEqual("HardwareIR", HardwareIR.__name__)
        self.assertIn("default", [item["id"] for item in list_workflows()])

    def test_backend_compatibility_wrappers_reexport_core_objects(self) -> None:
        import backend.agents.orchestrator as backend_orchestrator
        import backend.llm_providers as backend_llm
        import backend.models as backend_models
        import backend.validation as backend_validation
        from blueprint_core.agents import orchestrator as core_orchestrator
        from blueprint_core import models as core_models
        from blueprint_core import validation as core_validation
        from blueprint_core import llm as core_llm

        self.assertIs(backend_models.HardwareIR, core_models.HardwareIR)
        self.assertIs(backend_validation.validate_circuit, core_validation.validate_circuit)
        self.assertIs(backend_llm.resolve_llm_runtime_config, core_llm.resolve_llm_runtime_config)
        self.assertIs(
            backend_orchestrator.HardwarePipelineOrchestrator,
            core_orchestrator.HardwarePipelineOrchestrator,
        )


if __name__ == "__main__":
    unittest.main()
