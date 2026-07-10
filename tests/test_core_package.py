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
        self.assertEqual("backend.main:app", pyproject["tool"]["vercel"]["entrypoint"])
        self.assertEqual("blueprint_core._version.__version__", pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"])
        self.assertEqual("fabricator.main:main", pyproject["project"]["scripts"]["fabricator"])
        self.assertEqual("fibricator.main:main", pyproject["project"]["scripts"]["fibricator"])
        self.assertIn("blueprint_core", pyproject["tool"]["setuptools"]["packages"]["find"]["include"])
        self.assertIn("blueprint_core.*", pyproject["tool"]["setuptools"]["packages"]["find"]["include"])
        self.assertIn("fabricator", pyproject["tool"]["setuptools"]["packages"]["find"]["include"])
        self.assertIn("fibricator", pyproject["tool"]["setuptools"]["packages"]["find"]["include"])
        self.assertIn("py.typed", pyproject["tool"]["setuptools"]["package-data"]["blueprint_core"])
        self.assertIn("py.typed", pyproject["tool"]["setuptools"]["package-data"]["fabricator"])
        self.assertTrue((CORE_DIR / "py.typed").exists())
        self.assertTrue((ROOT_DIR / "fabricator" / "py.typed").exists())

    def test_backend_requirements_use_third_party_dependencies_for_vercel(self) -> None:
        requirements_path = ROOT_DIR / "backend" / "requirements.txt"
        requirements = [
            line.split("#", 1)[0].strip()
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
        ]
        active_requirements = [line for line in requirements if line]

        self.assertIn("fastapi>=0.124.1", active_requirements)
        self.assertIn("uvicorn", active_requirements)
        self.assertIn("websockets>=12.0", active_requirements)
        self.assertIn("pydantic>=2.12.0", active_requirements)
        self.assertIn("python-dotenv>=1.0.1", active_requirements)
        self.assertIn("sqlalchemy==2.0.31", active_requirements)
        self.assertIn("supabase==2.31.0", active_requirements)
        self.assertNotIn(".[backend]", active_requirements)
        for requirement in active_requirements:
            self.assertFalse(
                requirement.startswith((".", "-e", "file:")),
                "backend/requirements.txt is resolved from backend/ on Vercel; "
                f"local project requirement {requirement!r} would point at backend/backend.",
            )
        self.assertFalse(any(line.startswith(f"{DIST_NAME}==") for line in active_requirements))

    def test_root_requirements_avoid_local_paths_for_vercel(self) -> None:
        root_requirements = [
            line.split("#", 1)[0].strip()
            for line in (ROOT_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
        ]
        backend_requirements = [
            line.split("#", 1)[0].strip()
            for line in (ROOT_DIR / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines()
        ]

        root_active = [line for line in root_requirements if line]
        backend_active = [line for line in backend_requirements if line]

        self.assertEqual(backend_active, root_active)
        for requirement in root_active:
            self.assertFalse(requirement.startswith((".", "-e", "file:")))

    def test_pyproject_backend_extra_contains_fastapi_service_dependencies(self) -> None:
        pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        backend_deps = set(pyproject["project"]["optional-dependencies"]["backend"])

        self.assertIn("fastapi>=0.124.1", backend_deps)
        self.assertIn("uvicorn", backend_deps)
        self.assertIn("websockets>=12.0", backend_deps)
        self.assertIn("supabase==2.31.0", backend_deps)

    def test_vercel_backend_uses_standard_dependency_discovery(self) -> None:
        vercel_config = json.loads((ROOT_DIR / "vercel.json").read_text(encoding="utf-8"))

        self.assertNotIn("experimentalServices", vercel_config)
        backend = vercel_config["services"]["backend"]
        self.assertEqual(".", backend["root"])
        self.assertEqual("fastapi", backend["framework"])
        self.assertEqual("backend.main:app", backend["entrypoint"])
        self.assertNotIn("installCommand", backend)
        for function_key in ("backend.main:app", "backend/main.py", "main.py"):
            function_config = backend["functions"][function_key]
            self.assertEqual("blueprint_core/**", function_config["includeFiles"])
            exclude_files = function_config["excludeFiles"]
            self.assertIn("frontend/**", exclude_files)
            self.assertIn("rust/**", exclude_files)
            self.assertIn("*.db", exclude_files)
        self.assertNotIn("functions", vercel_config)
        self.assertIn(
            {"source": "/api/(.*)", "destination": {"service": "backend"}},
            vercel_config["rewrites"],
        )

    def test_root_main_shim_exports_backend_app_for_legacy_vercel_detection(self) -> None:
        import backend.main as backend_main
        import main as root_main

        self.assertIs(root_main.app, backend_main.app)
        self.assertIs(root_main.application, backend_main.app)

    def test_installed_distribution_metadata_when_available(self) -> None:
        try:
            distribution = importlib.metadata.distribution(DIST_NAME)
        except importlib.metadata.PackageNotFoundError:
            self.skipTest(f"{DIST_NAME} is not installed in this interpreter")

        import_path = pathlib.Path(blueprint_core.__file__).resolve()
        distribution_root = pathlib.Path(distribution.locate_file("")).resolve()
        if not import_path.is_relative_to(distribution_root):
            self.skipTest(f"{DIST_NAME} distribution metadata belongs to {distribution_root}, but source import is {import_path}")

        self.assertEqual(blueprint_core.__version__, distribution.version)

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
