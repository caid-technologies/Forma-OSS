"""Native CAD generation from agent-authored HardwareIR."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from typing import Any
from uuid import uuid4

from forma_core.config import config
from forma_core.workspaces.projects.models import HardwareIR
from forma_core.workspaces.projects.state import ProjectArtifact


CAD_ADAPTER_RELATIVE_PATH = Path(".agents") / "skills" / "forma-hardware" / "scripts" / "cad.py"
CAD_ADAPTER_NAME = "forma-opencad"
PLACEMENT_FALLBACK_ADAPTER = "forma-mechanical-layout"


class CadGenerationError(RuntimeError):
    """Raised when a required native CAD artifact cannot be generated."""


def _positive(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _project_dimensions(project: HardwareIR) -> tuple[float, float, float]:
    mechanical = project.mechanical
    render_dimensions = mechanical.render_dimensions if mechanical is not None else None
    if render_dimensions is not None:
        return (
            _positive(render_dimensions.x_mm, 80.0),
            _positive(render_dimensions.y_mm, 60.0),
            _positive(render_dimensions.z_mm, 30.0),
        )

    placements = mechanical.component_placements if mechanical is not None else []
    if placements:
        bounds = [
            (
                float(placement.position.x_mm) - abs(float(placement.size.x_mm)) / 2.0,
                float(placement.position.x_mm) + abs(float(placement.size.x_mm)) / 2.0,
                float(placement.position.y_mm) - abs(float(placement.size.y_mm)) / 2.0,
                float(placement.position.y_mm) + abs(float(placement.size.y_mm)) / 2.0,
                float(placement.position.z_mm) - abs(float(placement.size.z_mm)) / 2.0,
                float(placement.position.z_mm) + abs(float(placement.size.z_mm)) / 2.0,
            )
            for placement in placements
        ]
        return tuple(
            max(20.0, max(item[index + 1] for item in bounds) - min(item[index] for item in bounds) + 12.0)
            for index in (0, 2, 4)
        )  # type: ignore[return-value]

    return 80.0, 60.0, 30.0


def _placement_payload(project: HardwareIR) -> list[dict[str, Any]]:
    mechanical = project.mechanical
    if mechanical is None:
        return []
    return [
        {
            "ref_des": placement.ref_des,
            "label": placement.label or "",
            "category": placement.category or "",
            "x": float(placement.position.x_mm),
            "y": float(placement.position.y_mm),
            "z": float(placement.position.z_mm),
            "sx": max(1.0, abs(float(placement.size.x_mm))),
            "sy": max(1.0, abs(float(placement.size.y_mm))),
            "sz": max(1.0, abs(float(placement.size.z_mm))),
        }
        for placement in mechanical.component_placements
    ]


def _cad_source(project: HardwareIR) -> str:
    width, depth, height = _project_dimensions(project)
    mechanical = project.mechanical
    enclosure_text = " ".join(
        (
            str(mechanical.physical_form if mechanical is not None else ""),
            str(mechanical.enclosure_type if mechanical is not None else ""),
        )
    ).lower()
    open_frame = "open" in enclosure_text and "enclosure" not in enclosure_text
    wall = max(1.5, min(3.0, min(width, depth, height) / 12.0))
    placements = json.dumps(_placement_payload(project), sort_keys=True)
    return """from opencad import Part, Sketch


def xy_prism(x, y, z, length, width, height, name):
    profile = Sketch(plane="XY", origin=(0.0, 0.0, z), name=name + " profile")
    profile.rect(length, width, origin=(x, y))
    return Part(name=name).extrude(profile, depth=height, name=name)


def xz_prism(x, y, z, width, height, depth, name):
    profile = Sketch(plane="XZ", origin=(0.0, y, 0.0), name=name + " profile")
    profile.rect(width, height, origin=(x, z))
    return Part(name=name).extrude(profile, depth=depth, name=name)


def yz_prism(x, y, z, width, height, depth, name):
    profile = Sketch(plane="YZ", origin=(x, 0.0, 0.0), name=name + " profile")
    profile.rect(width, height, origin=(y, z))
    return Part(name=name).extrude(profile, depth=depth, name=name)


def xz_round_prism(x, y, z, radius, depth, name):
    profile = Sketch(plane="XZ", origin=(0.0, y, 0.0), name=name + " profile")
    profile.circle(radius, center=(x, z))
    return Part(name=name).extrude(profile, depth=depth, name=name)


def clamp(value, lower, upper):
    return max(lower, min(value, upper))


WIDTH = %r
DEPTH = %r
HEIGHT = %r
WALL = %r
OPEN_FRAME = %r
PLACEMENTS = %s

if OPEN_FRAME:
    model = xy_prism(-WIDTH / 2.0, -DEPTH / 2.0, -HEIGHT / 2.0, WIDTH, DEPTH, WALL, "Open frame base")
else:
    outer = xy_prism(-WIDTH / 2.0, -DEPTH / 2.0, -HEIGHT / 2.0, WIDTH, DEPTH, HEIGHT, "Beacon outer envelope")
    cavity = xy_prism(
        -WIDTH / 2.0 + WALL,
        -DEPTH / 2.0 + WALL,
        -HEIGHT / 2.0 + WALL,
        WIDTH - 2.0 * WALL,
        DEPTH - 2.0 * WALL,
        HEIGHT,
        "Open interior cavity",
    )
    model = outer.cut(cavity, name="Enclosure tray")

display = next((item for item in PLACEMENTS if "display" in (item["category"] + " " + item["label"]).lower() or "oled" in item["label"].lower()), None)
if display and not OPEN_FRAME:
    opening_width = clamp(display["sx"], 8.0, WIDTH - 4.0 * WALL)
    opening_height = clamp(display["sz"], 8.0, HEIGHT - 4.0 * WALL)
    opening_x = clamp(display["x"] - opening_width / 2.0, -WIDTH / 2.0 + WALL, WIDTH / 2.0 - WALL - opening_width)
    opening_z = clamp(display["z"] - opening_height / 2.0, -HEIGHT / 2.0 + WALL, HEIGHT / 2.0 - WALL - opening_height)
    display_cutout = xz_prism(opening_x, -DEPTH / 2.0 - 1.0, opening_z, opening_width, opening_height, WALL + 2.0, "OLED display cutout")
    model = model.cut(display_cutout, name="Front display opening")

    bezel_width = min(WIDTH - 2.0 * WALL, opening_width + 8.0)
    bezel_height = min(HEIGHT - 2.0 * WALL, opening_height + 8.0)
    bezel = xz_prism(
        display["x"] - bezel_width / 2.0,
        -DEPTH / 2.0 - WALL - 1.0,
        display["z"] - bezel_height / 2.0,
        bezel_width,
        bezel_height,
        WALL + 1.5,
        "OLED bezel",
    )
    bezel_hole = xz_prism(
        opening_x,
        -DEPTH / 2.0 - WALL - 2.0,
        opening_z,
        opening_width,
        opening_height,
        WALL + 4.0,
        "OLED bezel window",
    )
    model = model.union(bezel.cut(bezel_hole, name="OLED bezel frame"), name="Display bezel connected")

power = next((item for item in PLACEMENTS if "usb" in (item["category"] + " " + item["label"]).lower() or "power" in item["category"].lower()), None)
if power and not OPEN_FRAME:
    usb_width = clamp(min(power["sx"], 20.0), 8.0, WIDTH - 4.0 * WALL)
    usb_height = clamp(min(power["sz"], 12.0), 6.0, HEIGHT - 4.0 * WALL)
    usb_x = clamp(power["x"] - usb_width / 2.0, -WIDTH / 2.0 + WALL, WIDTH / 2.0 - WALL - usb_width)
    usb_z = clamp(power["z"] - usb_height / 2.0, -HEIGHT / 2.0 + WALL, HEIGHT / 2.0 - WALL - usb_height)
    usb_cutout = xz_prism(usb_x, DEPTH / 2.0 - 1.0, usb_z, usb_width, usb_height, WALL + 2.0, "USB entry cutout")
    model = model.cut(usb_cutout, name="Rear USB opening")

sensors = [item for item in PLACEMENTS if "sensor" in (item["category"] + " " + item["label"]).lower()]
if sensors and not OPEN_FRAME:
    for side, side_x in (("left", -WIDTH / 2.0 - 1.0), ("right", WIDTH / 2.0 - WALL + 1.0)):
        for slot_index, slot_y in enumerate((-DEPTH * 0.30, -DEPTH * 0.10, DEPTH * 0.10, DEPTH * 0.30), start=1):
            vent = yz_prism(side_x, slot_y - DEPTH * 0.045, 0.0, DEPTH * 0.09, 2.5, WALL + 2.0, side + " vent " + str(slot_index))
            model = model.cut(vent, name=side.title() + " ventilation slot " + str(slot_index))

led = next((item for item in PLACEMENTS if "led" in (item["category"] + " " + item["label"]).lower() or "rgb" in item["label"].lower()), None)
if led and not OPEN_FRAME:
    light = xz_round_prism(led["x"], -DEPTH / 2.0 - 1.0, led["z"], min(4.0, led["sx"] / 2.0), WALL + 2.0, "Status light opening")
    model = model.cut(light, name="Status light cutout")

for item in PLACEMENTS:
    if "enclosure" in (item["category"] + " " + item["label"]).lower():
        continue
    rail_width = clamp(item["sx"], 8.0, WIDTH - 2.0 * WALL)
    rail_depth = clamp(min(item["sy"], 4.0), 2.0, DEPTH - 2.0 * WALL)
    rail_x = clamp(item["x"] - rail_width / 2.0, -WIDTH / 2.0 + WALL, WIDTH / 2.0 - WALL - rail_width)
    rail_y = clamp(item["y"] - rail_depth / 2.0, -DEPTH / 2.0 + WALL, DEPTH / 2.0 - WALL - rail_depth)
    rail = xy_prism(rail_x, rail_y, -HEIGHT / 2.0 - 0.5, rail_width, rail_depth, max(2.0, min(item["sz"] / 2.0, HEIGHT / 3.0)), item["ref_des"] + " mounting rail")
    model = model.union(rail, name=item["ref_des"] + " rail connected")

model
""" % (width, depth, height, wall, open_frame, placements)


def _adapter_path() -> Path:
    configured = config.optional("FORMA_CAD_ADAPTER_PATH")
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        (
            Path(__file__).resolve().parents[3] / CAD_ADAPTER_RELATIVE_PATH,
            Path.cwd() / CAD_ADAPTER_RELATIVE_PATH,
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise CadGenerationError(
        "The Forma OpenCAD adapter is unavailable. Install the hardware skill or set "
        "FORMA_CAD_ADAPTER_PATH to its cad.py script."
    )


def _cad_workspace(project_id: str | None) -> Path:
    root = Path(config.optional("FORMA_CAD_WORKSPACE") or (Path.home() / "forma-workspace")).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    project_key = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in str(project_id or uuid4())
    ).strip("._") or str(uuid4())
    project_root = root / project_key / "cad"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "outputs").mkdir(exist_ok=True)
    return project_root


def _run_adapter(adapter: Path, model: Path, output: Path, tree: Path | None = None) -> dict[str, Any]:
    command = [sys.executable, str(adapter), "build", str(model), str(output), "--force"]
    if tree is not None:
        command.extend(("--tree-output", str(tree)))
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.number("FORMA_CAD_TIMEOUT_SECONDS", 900.0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CadGenerationError(f"OpenCAD generation could not complete: {exc}") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = (completed.stderr or completed.stdout or "unknown OpenCAD error").strip()
        if completed.returncode != 0:
            raise CadGenerationError(f"OpenCAD generation failed: {detail[-1200:]}") from exc
        raise CadGenerationError("OpenCAD adapter returned invalid build metadata.") from exc
    if not isinstance(payload, dict) or not payload.get("valid"):
        raise CadGenerationError("OpenCAD adapter did not return a valid CAD artifact.")
    if completed.returncode != 0 and not output.is_file():
        detail = (completed.stderr or completed.stdout or "unknown OpenCAD error").strip()
        raise CadGenerationError(f"OpenCAD generation failed: {detail[-1200:]}")
    return payload


def _stl_mesh(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    vertices: list[float] = []
    faces: list[int] = []
    vertex_ids: dict[tuple[float, float, float], int] = {}

    def add_triangle(points: list[tuple[float, float, float]]) -> None:
        if len(points) != 3:
            return
        face = []
        for point in points:
            vertex_id = vertex_ids.setdefault(point, len(vertices) // 3)
            if vertex_id == len(vertices) // 3:
                vertices.extend(point)
            face.append(vertex_id)
        faces.extend(face)

    binary_count = int.from_bytes(data[80:84], "little") if len(data) >= 84 else -1
    if binary_count >= 0 and 84 + binary_count * 50 == len(data):
        for index in range(binary_count):
            offset = 84 + index * 50 + 12
            add_triangle([struct.unpack_from("<3f", data, offset + point * 12) for point in range(3)])
    else:
        points: list[tuple[float, float, float]] = []
        for line in data.decode("ascii", errors="replace").splitlines():
            fields = line.strip().split()
            if len(fields) == 4 and fields[0].lower() == "vertex":
                points.append(tuple(float(value) for value in fields[1:4]))
                if len(points) == 3:
                    add_triangle(points)
                    points = []
    if not faces:
        raise CadGenerationError("OpenCAD STL preview contains no triangles.")
    return {
        "shapeId": "native-cad-model",
        "name": "Forma OpenCAD model",
        "vertices": vertices,
        "faces": faces,
    }


def _has_authoritative_cad(value: Any) -> bool:
    if value in (None, "", {}):
        return False
    if not isinstance(value, dict):
        return True
    adapter = str(value.get("adapter") or "").strip().lower()
    return adapter not in {PLACEMENT_FALLBACK_ADAPTER, "forma-test-tube-preview"}


def _cad_is_applicable(project: HardwareIR) -> bool:
    if project.mechanical is None:
        return False
    return bool(project.mechanical.component_placements or project.components or project.mechanical.render_dimensions)


def _set_cad_status(project: HardwareIR, *, status: str, required: bool, error: str | None = None) -> None:
    metadata = dict(project.assembly_metadata or {})
    cad = project.cad_model if isinstance(project.cad_model, dict) else {}
    record: dict[str, Any] = {
        "adapter": str(cad.get("adapter") or CAD_ADAPTER_NAME),
        "status": status,
        "required": required,
    }
    if error:
        record["error"] = error[:500]
    metadata["cad_generation"] = record
    project.assembly_metadata = metadata


def ensure_native_cad_model(
    project: HardwareIR,
    *,
    project_id: str | None,
    required: bool,
    authoring_agent: str | None = None,
    workflow: str | None = None,
) -> bool:
    """Generate native CAD when requested, preserving legacy optional behavior."""
    if _has_authoritative_cad(project.cad_model):
        _set_cad_status(project, status="provided", required=required)
        return False
    if not _cad_is_applicable(project):
        _set_cad_status(project, status="not_applicable", required=required)
        return False

    if workflow:
        from forma_core.agents.pipeline import emit_agent_pipeline_event

        emit_agent_pipeline_event(workflow, "cad_generation", "started", details={"required": required})
    try:
        root = _cad_workspace(project_id)
        model_path = root / "assembly.py"
        step_path = root / "outputs" / "assembly.step"
        stl_path = root / "outputs" / "assembly.stl"
        tree_path = root / "outputs" / "assembly.tree.json"
        model_path.write_text(_cad_source(project), encoding="utf-8")
        adapter = _adapter_path()
        step_summary = _run_adapter(adapter, model_path, step_path, tree_path)
        _run_adapter(adapter, model_path, stl_path)
        step_bytes = step_path.read_bytes()
        checksum = hashlib.sha256(step_bytes).hexdigest()
        project.cad_model = {
            "adapter": CAD_ADAPTER_NAME,
            "source": "Native OpenCAD generated from agent-authored HardwareIR",
            "authoring_agent": authoring_agent,
            "authoring_mode": "hardware-ir-to-opencad",
            "generated": True,
            "format": "step",
            "units": "mm",
            "filename": step_path.name,
            "path": str(step_path),
            "bytes": len(step_bytes),
            "sha256": checksum,
            "preview_filename": stl_path.name,
            "preview_path": str(stl_path),
            "model_source_path": str(model_path),
            "feature_tree_path": str(tree_path),
            "opencad_version": step_summary.get("opencad_version"),
            "meshes": [_stl_mesh(stl_path)],
        }
        _set_cad_status(project, status="succeeded", required=required)
        if workflow:
            from forma_core.agents.pipeline import emit_agent_pipeline_event

            emit_agent_pipeline_event(
                workflow,
                "cad_generation",
                "completed",
                details={"adapter": CAD_ADAPTER_NAME, "format": "step", "bytes": len(step_bytes)},
            )
        return True
    except Exception as exc:
        _set_cad_status(project, status="failed", required=required, error=str(exc))
        if workflow:
            from forma_core.agents.pipeline import emit_agent_pipeline_event

            emit_agent_pipeline_event(
                workflow,
                "cad_generation",
                "failed" if required else "skipped",
                details={"required": required, "error": str(exc)[:500]},
            )
        if required:
            if isinstance(exc, CadGenerationError):
                raise
            raise CadGenerationError(str(exc)) from exc
        return False


def cad_project_artifact(project: HardwareIR, project_id: str) -> ProjectArtifact | None:
    """Return the canonical revision artifact for a generated CAD model."""
    cad = project.cad_model
    if not isinstance(cad, dict) or str(cad.get("adapter") or "").strip().lower() != CAD_ADAPTER_NAME:
        return None
    checksum = str(cad.get("sha256") or "").strip()
    return ProjectArtifact(
        artifact_id="native-cad-model",
        kind="cad",
        uri=f"forma://projects/{project_id}/cad/assembly.step",
        media_type="model/step",
        checksum=f"sha256:{checksum}" if checksum and not checksum.startswith("sha256:") else checksum or None,
        metadata={
            "adapter": CAD_ADAPTER_NAME,
            "preview_path": cad.get("preview_path"),
            "model_source_path": cad.get("model_source_path"),
            "feature_tree_path": cad.get("feature_tree_path"),
            "format": cad.get("format", "step"),
        },
    )


__all__ = [
    "CAD_ADAPTER_NAME",
    "CadGenerationError",
    "cad_project_artifact",
    "ensure_native_cad_model",
]
