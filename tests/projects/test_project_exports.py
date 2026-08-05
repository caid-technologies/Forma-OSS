from __future__ import annotations

import base64
import hashlib
import re
import unittest

from blueprint_core.workspaces.projects.exports import (
    attach_project_output_artifacts,
    build_project_pdf_artifact,
    normalize_project_output_formats,
    render_project_pdf,
)
from blueprint_core.workspaces.projects.report_views import render_project_view_screenshots


SAMPLE_PROJECT = {
    "hardware_ir_version": "0.1",
    "overview": {
        "title": "ESP32 Soil Monitor",
        "description": "A 5V USB-powered plant monitor with a moisture sensor and OLED.",
        "difficulty": "Beginner",
        "estimated_cost": 24.5,
        "category": "IoT",
    },
    "requirements": {
        "requirements": ["Measure soil moisture", "Show status locally"],
        "power_needs": "5V USB",
        "operating_voltage": 3.3,
        "physical_constraints": ["Indoor enclosure"],
        "safety_notes": ["Disconnect USB power before rewiring."],
        "missing_info": [],
    },
    "components": [
        {
            "ref_des": "U1",
            "part_number": "ESP32-DEVKIT",
            "name": "ESP32 development board",
            "category": "Microcontroller",
            "quantity": 1,
            "unit_price": 9.5,
            "rationale": "Provides Wi-Fi and analog input.",
            "pins": [
                {
                    "pin_id": "3V3",
                    "name": "3V3",
                    "pin_type": "Power",
                    "voltage": 3.3,
                    "description": "Regulated 3.3V output",
                }
            ],
        }
    ],
    "nets": [
        {
            "net_id": "NET_3V3",
            "name": "3.3V rail",
            "net_type": "Power",
            "voltage": 3.3,
            "pins": [{"ref_des": "U1", "pin_id": "3V3"}],
        }
    ],
    "assembly": [
        {
            "step_num": 1,
            "title": "Wire power",
            "description": "Connect the sensor to the regulated 3.3V output.",
            "danger_flag": False,
        }
    ],
    "validation": {"critical": [], "warning": [], "info": []},
    "is_valid": True,
    "estimated_current_draw_ma": 180,
    "assembly_metadata": {"project_id": "project-123"},
}


class ProjectPdfExportTests(unittest.TestCase):
    def test_renderer_produces_a_structurally_complete_pdf(self) -> None:
        pdf = render_project_pdf(SAMPLE_PROJECT)

        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/Type /Catalog", pdf)
        self.assertIn(b"/Type /Pages", pdf)
        self.assertEqual(5, len(re.findall(rb"/Type /Page\b", pdf)))
        self.assertEqual(5, len(re.findall(rb"/Subtype /Image\b", pdf)))
        startxref = int(re.search(rb"startxref\n(\d+)\n%%EOF", pdf).group(1))
        self.assertEqual(b"xref", pdf[startxref:startxref + 4])

    def test_report_always_has_one_page_per_workspace_view(self) -> None:
        project = {**SAMPLE_PROJECT, "assembly": [
            {
                "step_num": index,
                "title": f"Assembly step {index}",
                "description": "Connect and verify the low-voltage wiring before proceeding. " * 4,
                "danger_flag": False,
            }
            for index in range(1, 80)
        ]}

        pdf = render_project_pdf(project)
        self.assertEqual(5, len(re.findall(rb"/Type /Page\b", pdf)))

    def test_workspace_screenshots_cover_expected_views(self) -> None:
        screenshots = render_project_view_screenshots(SAMPLE_PROJECT)

        self.assertEqual(["info", "bom", "mech", "wire", "docs"], [name for name, _data in screenshots])
        self.assertTrue(all(data.startswith(b"\x89PNG\r\n\x1a\n") for _name, data in screenshots))

    def test_artifact_has_integrity_metadata_and_base64_pdf(self) -> None:
        artifact = build_project_pdf_artifact(SAMPLE_PROJECT)
        pdf = base64.b64decode(artifact["data_base64"], validate=True)

        self.assertEqual("application/pdf", artifact["mime_type"])
        self.assertEqual("esp32_soil_monitor_report.pdf", artifact["filename"])
        self.assertEqual(len(pdf), artifact["size_bytes"])
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), artifact["sha256"])
        self.assertEqual("forma://artifacts/project-123/esp32_soil_monitor_report.pdf", artifact["uri"])
        self.assertEqual(["info", "bom", "mech", "wire", "docs"], artifact["views"])
        self.assertEqual("workspace_screenshots", artifact["rendering"])

    def test_requested_filename_is_sanitized_without_adding_a_suffix(self) -> None:
        artifact = build_project_pdf_artifact(SAMPLE_PROJECT, requested_filename="../Customer Report.PDF")

        self.assertEqual("customer_report.pdf", artifact["filename"])
        self.assertNotIn("..", artifact["uri"])

    def test_generation_artifacts_are_only_added_when_requested(self) -> None:
        response = {"project_id": "project-123", "project_ir": SAMPLE_PROJECT}

        self.assertIs(response, attach_project_output_artifacts(response, None))
        exported = attach_project_output_artifacts(response, ["PDF", "pdf"])

        self.assertEqual(["pdf"], exported["output_formats"])
        self.assertEqual(1, len(exported["artifacts"]))
        self.assertNotIn("artifacts", response)

    def test_unknown_output_format_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported project output format"):
            normalize_project_output_formats(["docx"])


if __name__ == "__main__":
    unittest.main()
