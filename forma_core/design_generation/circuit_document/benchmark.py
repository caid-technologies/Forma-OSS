"""Deterministic architecture fixture; it is not a production response path."""

from __future__ import annotations

from pydantic import BaseModel

from forma_core.design_generation.circuit_document.models import CircuitDocument
from forma_core.design_generation.circuit_document.projections import (
    CircuitProjectionService,
)
from forma_core.design_generation.state_machine.models import GenerationStatus

ENVIRONMENTAL_MONITOR_PROMPT = (
    "Design a compact desktop environmental monitor using an ESP32, "
    "a temperature and humidity sensor, an OLED display, and USB-C power."
)

ENVIRONMENTAL_MONITOR_DOCUMENT = CircuitDocument(
    text="""MACHINE environmental-monitor
GOAL measure temperature and humidity and display the readings
CONSTRAINT mechanical.form | compact-desktop
CONSTRAINT power.input | USB-C 5V
CONSTRAINT power.logic | 3V3
BLOCK control | ESP32 module with reset and programming support
BLOCK display | I2C OLED
BLOCK mechanical | Ventilated enclosure containing one PCB
BLOCK power | Protected USB-C input with 3V3 regulation
BLOCK sensing | I2C temperature and humidity sensor
ROLE bus.i2c-pullups | required | selected | 2x4.7k
ROLE control.decoupling | required | selected | 100nF
ROLE control.en-reset | required | selected | 10k and 1uF
ROLE control.mcu | required | selected | ESP32-WROOM-32E-N4
ROLE display.oled | required | selected | UG-2864HSWEG01
ROLE mechanical.enclosure | required | selected | CUSTOM-VENTED-ENCLOSURE
ROLE mechanical.mounting | required | selected | M2.5-NYLON-STANDOFF
ROLE mechanical.pcb | required | selected | CUSTOM-2L-PCB
ROLE power.input-cap | required | selected | GRM21BR61A106KE19L
ROLE power.output-cap | required | selected | GRM21BR61A106KE19L
ROLE power.regulator | required | selected | AP2112K-3.3TRG1
ROLE programming.bridge | required | selected | CP2102N-A02-GQFN28
ROLE programming.controls | required | selected | TL3301NF160QG
ROLE sensing.decoupling | required | selected | GRM188R71C104KA01D
ROLE sensing.sensor | required | selected | SHT40-AD1B-R2
ROLE usb.cc-pulldowns | required | selected | 2x5.1k
ROLE usb.connector | required | selected | USB4085-GF-A
ROLE usb.esd | required | selected | TPD4E05U06DQAR
PART C1 | role=power.input-cap | part=GRM21BR61A106KE19L | qty=1
PART C2 | role=power.output-cap | part=GRM21BR61A106KE19L | qty=1
PART C3 | role=control.decoupling | part=GRM188R71C104KA01D | qty=1
PART C4 | role=sensing.decoupling | part=GRM188R71C104KA01D | qty=1
PART ENC1 | role=mechanical.enclosure | part=CUSTOM-VENTED-ENCLOSURE | qty=1
PART H1-H4 | role=mechanical.mounting | part=M2.5-NYLON-STANDOFF | qty=4
PART J1 | role=usb.connector | part=USB4085-GF-A | qty=1
PART OLED1 | role=display.oled | part=UG-2864HSWEG01 | qty=1
PART PCB1 | role=mechanical.pcb | part=CUSTOM-2L-PCB | qty=1
PART R1-R2 | role=usb.cc-pulldowns | part=RC0603FR-075K1L | qty=2
PART R3-R4 | role=bus.i2c-pullups | part=RC0603FR-074K7L | qty=2
PART R5 | role=control.en-reset | part=RC0603FR-0710KL | qty=1
PART SEN1 | role=sensing.sensor | part=SHT40-AD1B-R2 | qty=1
PART SW1-SW2 | role=programming.controls | part=TL3301NF160QG | qty=2
PART U1 | role=power.regulator | part=AP2112K-3.3TRG1 | qty=1
PART U2 | role=control.mcu | part=ESP32-WROOM-32E-N4 | qty=1
PART U3 | role=programming.bridge | part=CP2102N-A02-GQFN28 | qty=1
PART U4 | role=usb.esd | part=TPD4E05U06DQAR | qty=1
NET 3V3 | U1.VOUT U2.3V3 SEN1.VDD OLED1.VCC
NET 5V | J1.VBUS U1.VIN
NET GND | J1.GND U1.GND U2.GND SEN1.VSS OLED1.GND
NET I2C_SCL | U2.GPIO22 SEN1.SCL OLED1.SCL pullup=3V3
NET I2C_SDA | U2.GPIO21 SEN1.SDA OLED1.SDA pullup=3V3"""
)


class CircuitBenchmarkReport(BaseModel):
    character_count: int
    raw_bom_lines: int
    physical_quantity: int
    required_role_coverage: float
    open_issues: int
    parse_or_patch_failures: int
    final_status: GenerationStatus


def environmental_monitor_benchmark_report() -> CircuitBenchmarkReport:
    projection = CircuitProjectionService().build(ENVIRONMENTAL_MONITOR_DOCUMENT)
    completeness = projection.completeness
    return CircuitBenchmarkReport(
        character_count=len(ENVIRONMENTAL_MONITOR_DOCUMENT.text),
        raw_bom_lines=completeness.raw_bom_line_count,
        physical_quantity=completeness.physical_component_quantity,
        required_role_coverage=completeness.required_role_coverage,
        open_issues=completeness.open_issue_count,
        parse_or_patch_failures=0,
        final_status=GenerationStatus.COMPLETE,
    )


__all__ = [
    "ENVIRONMENTAL_MONITOR_DOCUMENT",
    "ENVIRONMENTAL_MONITOR_PROMPT",
    "CircuitBenchmarkReport",
    "environmental_monitor_benchmark_report",
]
