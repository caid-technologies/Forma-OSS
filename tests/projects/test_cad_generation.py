from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forma_core.config import config
from forma_core.workspaces.projects.cad_generation import (
    CadGenerationError,
    _cad_source,
    cad_project_artifact,
    ensure_native_cad_model,
)
from forma_core.workspaces.projects.models import (
    ComponentInstance,
    HardwareIR,
    MechanicalNotes,
    MechanicalPlacement,
    MechanicalVector3,
)


def mechanical_project() -> HardwareIR:
    return HardwareIR(
        mechanical=MechanicalNotes(
            enclosure_type="Open frame",
            mounting_guidance="Use a flat base plate.",
            manufacturability_rating="Easy",
            render_dimensions=MechanicalVector3(x_mm=80, y_mm=60, z_mm=30),
        )
    )


def complex_mechanical_project() -> HardwareIR:
    placements = [
        MechanicalPlacement(
            ref_des=f"U{index}",
            label=f"Module {index}",
            category="Controller" if index % 4 == 0 else "Power",
            position=MechanicalVector3(
                x_mm=-55 + (index % 4) * 36,
                y_mm=-25 + (index // 4) * 18,
                z_mm=-14 + (index % 3) * 12,
            ),
            size=MechanicalVector3(
                x_mm=18 + (index % 3) * 7,
                y_mm=12 + (index % 2) * 5,
                z_mm=8 + (index % 4) * 3,
            ),
        )
        for index in range(1, 17)
    ]
    placements.extend([
        MechanicalPlacement(
            ref_des="DISP1",
            label="OLED 2.8 inch display",
            category="Display",
            position=MechanicalVector3(x_mm=0, y_mm=-48, z_mm=4),
            size=MechanicalVector3(x_mm=48, y_mm=5, z_mm=28),
        ),
        MechanicalPlacement(
            ref_des="PWR1",
            label="USB-C rear power input",
            category="Power",
            position=MechanicalVector3(x_mm=0, y_mm=48, z_mm=-3),
            size=MechanicalVector3(x_mm=16, y_mm=8, z_mm=10),
        ),
        *[
            MechanicalPlacement(
                ref_des=f"SEN{index}",
                label=f"{label} sensor",
                category="Sensor",
                position=MechanicalVector3(x_mm=-42 + (index - 1) * 28, y_mm=0, z_mm=12),
                size=MechanicalVector3(x_mm=18, y_mm=14, z_mm=8),
            )
            for index, label in enumerate(("Air quality", "Temperature", "Humidity", "Pressure"), start=1)
        ],
        MechanicalPlacement(
            ref_des="LED1",
            label="RGB status LED",
            category="Indicator",
            position=MechanicalVector3(x_mm=52, y_mm=-48, z_mm=-12),
            size=MechanicalVector3(x_mm=8, y_mm=4, z_mm=8),
        ),
        MechanicalPlacement(
            ref_des="ENC1",
            label="Outer enclosure",
            category="Enclosure",
            position=MechanicalVector3(x_mm=0, y_mm=0, z_mm=0),
            size=MechanicalVector3(x_mm=160, y_mm=110, z_mm=50),
        ),
    ])
    components = [
        ComponentInstance(
            ref_des=placement.ref_des,
            part_number=f"STRESS-{placement.ref_des}",
            name=placement.label or placement.ref_des,
            category=placement.category or "Mechanical",
            rationale="Complex CAD stress fixture component",
        )
        for placement in placements
    ]
    return HardwareIR(
        components=components,
        mechanical=MechanicalNotes(
            physical_form="Curved desktop instrument enclosure",
            enclosure_type="3D printed enclosure",
            mounting_guidance="Use internal rails and serviceable rear access.",
            fabrication_details=[
                "Print shell in two halves with internal rails.",
                "Keep sensor vents open on both side walls.",
            ],
            manufacturability_rating="Moderate",
            render_dimensions=MechanicalVector3(x_mm=160, y_mm=110, z_mm=50),
            component_placements=placements,
        ),
    )


class CadGenerationTests(unittest.TestCase):
    def test_required_generation_publishes_native_model_and_revision_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            def fake_run(_adapter: Path, _model: Path, output: Path, tree: Path | None = None) -> dict:
                if output.suffix == ".step":
                    output.write_bytes(b"ISO-10303-21;HEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;")
                else:
                    output.write_text(
                        "solid model\n"
                        "facet normal 0 0 1\n"
                        "outer loop\n"
                        "vertex 0 0 0\n"
                        "vertex 1 0 0\n"
                        "vertex 0 1 0\n"
                        "endloop\nendfacet\nendsolid model\n",
                        encoding="ascii",
                    )
                if tree is not None:
                    tree.write_text("{}", encoding="utf-8")
                return {"valid": True, "opencad_version": "0.2.3"}

            project = mechanical_project()
            with patch.dict("os.environ", {"FORMA_CAD_WORKSPACE": workspace}, clear=False), patch(
                "forma_core.workspaces.projects.cad_generation._adapter_path",
                return_value=Path(__file__),
            ), patch(
                "forma_core.workspaces.projects.cad_generation._run_adapter",
                side_effect=fake_run,
            ):
                self.assertTrue(ensure_native_cad_model(
                    project,
                    project_id="11111111-1111-4111-8111-111111111111",
                    required=True,
                ))

            self.assertEqual("forma-opencad", project.cad_model["adapter"])
            self.assertEqual("succeeded", project.assembly_metadata["cad_generation"]["status"])
            artifact = cad_project_artifact(project, "11111111-1111-4111-8111-111111111111")
            self.assertIsNotNone(artifact)
            self.assertEqual("model/step", artifact.media_type)
            self.assertTrue(artifact.checksum.startswith("sha256:"))

    def test_legacy_generation_failure_is_best_effort(self) -> None:
        project = mechanical_project()
        with patch(
            "forma_core.workspaces.projects.cad_generation._adapter_path",
            side_effect=CadGenerationError("adapter unavailable"),
        ):
            self.assertFalse(ensure_native_cad_model(
                project,
                project_id="22222222-2222-4222-8222-222222222222",
                required=False,
            ))

        self.assertEqual("failed", project.assembly_metadata["cad_generation"]["status"])
        self.assertFalse(project.cad_model)

    def test_new_generation_failure_is_reported_as_required(self) -> None:
        project = mechanical_project()
        with patch(
            "forma_core.workspaces.projects.cad_generation._adapter_path",
            side_effect=CadGenerationError("adapter unavailable"),
        ):
            with self.assertRaises(CadGenerationError):
                ensure_native_cad_model(
                    project,
                    project_id="33333333-3333-4333-8333-333333333333",
                    required=True,
                )

        self.assertEqual("failed", project.assembly_metadata["cad_generation"]["status"])

    def test_complex_mechanical_source_covers_cutouts_vents_and_mounting_rails(self) -> None:
        source = _cad_source(complex_mechanical_project())

        self.assertEqual(24, source.count('"ref_des":'))
        for feature in (
            "Front display opening",
            "OLED bezel",
            "Rear USB opening",
            "ventilation slot",
            "Status light cutout",
            "mounting rail",
        ):
            self.assertIn(feature, source)

    @unittest.skipUnless(
        config.boolean("FORMA_CAD_RUN_INTEGRATION_TESTS"),
        "Set FORMA_CAD_RUN_INTEGRATION_TESTS=true to run native OpenCAD integration tests.",
    )
    def test_complex_mechanical_model_exports_with_native_opencad(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            with patch.dict("os.environ", {"FORMA_CAD_WORKSPACE": workspace}, clear=False):
                project = complex_mechanical_project()
                self.assertTrue(ensure_native_cad_model(
                    project,
                    project_id="77777777-7777-4777-8777-777777777777",
                    required=True,
                    authoring_agent="OpenCAD stress fixture",
                ))

        self.assertEqual("forma-opencad", project.cad_model["adapter"])
        self.assertGreater(project.cad_model["bytes"], 500_000)
        self.assertGreater(len(project.cad_model["meshes"][0]["faces"]), 900)


if __name__ == "__main__":
    unittest.main()
