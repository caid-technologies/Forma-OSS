# Agent-authored Forma Hardware IR

Author a concrete, internally consistent project. Use real reference designators and pin IDs. Every net pin must point to a declared component pin. Include enough pin definitions for deterministic voltage, short-circuit, and conflict checks.

Start from this shape:

```json
{
  "hardware_ir_version": "0.1",
  "overview": {
    "title": "Project title",
    "description": "What the prototype does and its safe scope",
    "difficulty": "Beginner",
    "estimated_cost": 0,
    "category": "IoT"
  },
  "requirements": {
    "requirements": ["Measurable functional requirement"],
    "power_needs": "5V USB",
    "operating_voltage": 3.3,
    "physical_constraints": [],
    "safety_notes": ["Disconnect power before rewiring."],
    "missing_info": []
  },
  "components": [
    {
      "ref_des": "U1",
      "part_number": "ESP32-DEVKIT",
      "name": "ESP32 development board",
      "category": "Microcontroller",
      "quantity": 1,
      "unit_price": 9.5,
      "sourcing_url": null,
      "rationale": "Controls the prototype.",
      "pins": [
        {"pin_id": "3V3", "name": "3V3", "pin_type": "Power", "voltage": 3.3, "description": "Regulated output"},
        {"pin_id": "GND", "name": "GND", "pin_type": "Ground", "voltage": 0, "description": "Ground"}
      ]
    }
  ],
  "nets": [
    {
      "net_id": "NET_3V3",
      "name": "3.3V rail",
      "net_type": "Power",
      "voltage": 3.3,
      "pins": [{"ref_des": "U1", "pin_id": "3V3"}]
    }
  ],
  "buses": [],
  "pin_mappings": [],
  "assembly": [
    {
      "step_num": 1,
      "title": "Wire power while disconnected",
      "description": "Connect the declared low-voltage rails and inspect polarity before power-up.",
      "danger_flag": false,
      "danger_message": null,
      "affected_components": ["U1"]
    }
  ],
  "mechanical": {
    "enclosure_type": "3D printed",
    "mounting_guidance": "Use insulated standoffs and preserve connector access.",
    "fabrication_details": ["Verify dimensions against physical parts."],
    "fabrication_cost_estimate_usd": 5,
    "cad_sources": [],
    "manufacturability_rating": "Easy",
    "render_dimensions": {"x_mm": 80, "y_mm": 55, "z_mm": 25},
    "component_placements": [],
    "spatial_relationships": []
  },
  "constraints": ["Low-voltage DC only"],
  "power_rails": [],
  "estimated_current_draw_ma": 250,
  "fabrication_notes": [],
  "assembly_metadata": {},
  "project_version_history": [],
  "validation": {"critical": [], "warning": [], "info": []},
  "is_valid": true
}
```

Use these `pin_type` values where applicable: `Power`, `Ground`, `Digital`, `Analog`, `I2C`, `SPI`, `UART`, `PWM`, or `Passive`.

Before compiling, check:

- Reference designators and net IDs are unique.
- Every connected `ref_des.pin_id` exists in `components[].pins`.
- Power and signal voltages are compatible.
- BOM quantities, unit prices, and rationale are present.
- Assembly steps explain wiring, inspection, initial current-limited power-up, and testing.
- Mechanical notes describe clearances as estimates unless verified against real CAD.
