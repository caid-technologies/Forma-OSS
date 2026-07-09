from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class DashboardRenderConfig:
    width: int = 1280
    height: int = 900
    background: tuple[int, int, int] = (15, 17, 23)
    scene_yaw_degrees: float = 0.0
    scene_label: str = "LIVE 3D / TERMINAL"


@dataclass(frozen=True)
class RenderVector:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class RenderPlacement:
    ref_des: str
    label: str
    category: str
    layer: str
    position: RenderVector
    size: RenderVector


@dataclass(frozen=True)
class RenderSummary:
    title: str
    description: str
    project_id: str
    provider: str
    model: str
    component_count: int
    net_count: int
    estimated_cost: float
    image_status: str


CATEGORY_COLORS: Mapping[str, tuple[int, int, int]] = {
    "microcontroller": (34, 211, 238),
    "sensor": (52, 211, 153),
    "actuator": (251, 146, 60),
    "display": (236, 72, 153),
    "power": (250, 204, 21),
    "passives": (167, 139, 250),
    "communication": (96, 165, 250),
    "mechanical": (251, 113, 133),
    "3d print": (129, 140, 248),
    "default": (148, 163, 184),
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None and str(value).strip() else default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _category_key(value: Any) -> str:
    key = _text(value, "default").lower()
    return key if key in CATEGORY_COLORS else "default"


def _vector(value: Any, default: RenderVector) -> RenderVector:
    data = _mapping(value)
    return RenderVector(
        x=_number(data.get("x_mm", data.get("x")), default.x),
        y=_number(data.get("y_mm", data.get("y")), default.y),
        z=_number(data.get("z_mm", data.get("z")), default.z),
    )


def _placement_size_for_component(component: Mapping[str, Any]) -> RenderVector:
    name = f"{component.get('name') or ''} {component.get('part_number') or ''}".lower()
    category = _category_key(component.get("category"))
    if "battery" in name:
        return RenderVector(48, 26, 8)
    if "speaker" in name:
        return RenderVector(24, 24, 10)
    if "relay" in name:
        return RenderVector(38, 26, 16)
    if "oled" in name or "display" in name:
        return RenderVector(34, 18, 4)
    if "button" in name or "switch" in name:
        return RenderVector(10, 10, 7)
    defaults = {
        "microcontroller": RenderVector(38, 28, 5),
        "sensor": RenderVector(20, 18, 8),
        "actuator": RenderVector(30, 24, 14),
        "display": RenderVector(32, 18, 4),
        "power": RenderVector(42, 24, 8),
        "mechanical": RenderVector(16, 16, 8),
        "3d print": RenderVector(26, 20, 8),
    }
    return defaults.get(category, RenderVector(22, 18, 6))


def _generated_position(index: int, total: int, dimensions: RenderVector) -> RenderVector:
    columns = max(1, math.ceil(math.sqrt(max(total, 1))))
    row = index // columns
    column = index % columns
    x = ((column / max(columns - 1, 1)) - 0.5) * dimensions.x * 0.64
    y = ((row / max(columns - 1, 1)) - 0.5) * dimensions.y * 0.58
    z = -dimensions.z * 0.15 + (index % 3) * min(7, dimensions.z * 0.12)
    return RenderVector(x, y, z)


def _placements(project_ir: Mapping[str, Any], dimensions: RenderVector) -> tuple[RenderPlacement, ...]:
    mechanical = _mapping(project_ir.get("mechanical"))
    components = tuple(_mapping(item) for item in _sequence(project_ir.get("components")))
    by_ref = {_text(component.get("ref_des"), f"C{index + 1}"): component for index, component in enumerate(components)}
    placements: list[RenderPlacement] = []

    for item in _sequence(mechanical.get("component_placements")):
        data = _mapping(item)
        ref = _text(data.get("ref_des") or data.get("ref"))
        if not ref:
            continue
        component = by_ref.get(ref, {})
        label = _text(data.get("label") or component.get("name") or component.get("part_number"), ref)
        category = _text(data.get("category") or component.get("category"), "default")
        placements.append(
            RenderPlacement(
                ref_des=ref,
                label=label,
                category=category,
                layer=_text(data.get("layer"), "electrical"),
                position=_vector(data.get("position_mm") or data.get("position"), RenderVector(0, 0, 0)),
                size=_vector(data.get("size_mm") or data.get("size"), _placement_size_for_component(component)),
            )
        )

    existing = {placement.ref_des for placement in placements}
    for index, component in enumerate(components):
        ref = _text(component.get("ref_des"), f"C{index + 1}")
        if ref in existing:
            continue
        placements.append(
            RenderPlacement(
                ref_des=ref,
                label=_text(component.get("name") or component.get("part_number"), ref),
                category=_text(component.get("category"), "default"),
                layer="electrical",
                position=_generated_position(index, len(components), dimensions),
                size=_placement_size_for_component(component),
            )
        )

    return tuple(placements)


def _summary(project_ir: Mapping[str, Any], *, subtitle: str = "") -> RenderSummary:
    overview = _mapping(project_ir.get("overview"))
    metadata = _mapping(project_ir.get("assembly_metadata"))
    components = _sequence(project_ir.get("components"))
    nets = _sequence(project_ir.get("nets"))
    image_status = _text(metadata.get("image_output_status") or metadata.get("product_image_status"), "not requested")
    return RenderSummary(
        title=_text(overview.get("title"), "Untitled Hardware Project"),
        description=_text(overview.get("description"), subtitle or "Generated hardware package"),
        project_id=_text(metadata.get("project_id")),
        provider=_text(metadata.get("runtime_provider") or metadata.get("llm_provider") or metadata.get("requested_provider")),
        model=_text(metadata.get("runtime_model") or metadata.get("actual_model") or metadata.get("model_name") or metadata.get("requested_model")),
        component_count=len(components),
        net_count=len(nets),
        estimated_cost=_number(overview.get("estimated_cost"), 0.0),
        image_status=image_status,
    )


def _dimensions(project_ir: Mapping[str, Any]) -> RenderVector:
    mechanical = _mapping(project_ir.get("mechanical"))
    metadata = _mapping(project_ir.get("assembly_metadata"))
    visual_spec = _mapping(metadata.get("product_visual_spec"))
    return _vector(
        mechanical.get("render_dimensions")
        or visual_spec.get("external_dimensions_mm")
        or metadata.get("render_dimensions"),
        RenderVector(100, 65, 38),
    )


def _font(size: int, *, bold: bool = False) -> Any:
    from PIL import ImageFont

    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(draw: Any, text: str, *, x: int, y: int, width: int, fill: tuple[int, int, int], font: Any, line_gap: int = 6, max_lines: int = 4) -> int:
    approx_chars = max(12, width // max(8, int(getattr(font, "size", 12) * 0.58)))
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        lines.extend(textwrap.wrap(paragraph, width=approx_chars) or [""])
    for line in lines[:max_lines]:
        draw.text((x, y), line, fill=fill, font=font)
        y += getattr(font, "size", 12) + line_gap
    return y


def _fit_text(draw: Any, text: str, *, max_width: int, font: Any) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "..."
    candidate = text
    while candidate and draw.textlength(candidate + ellipsis, font=font) > max_width:
        candidate = candidate[:-1]
    return (candidate.rstrip() + ellipsis) if candidate else ellipsis


def _shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _rotate_xy(point: RenderVector, *, yaw_degrees: float) -> RenderVector:
    if not yaw_degrees:
        return point
    radians = math.radians(yaw_degrees)
    cos_yaw = math.cos(radians)
    sin_yaw = math.sin(radians)
    return RenderVector(
        x=point.x * cos_yaw - point.y * sin_yaw,
        y=point.x * sin_yaw + point.y * cos_yaw,
        z=point.z,
    )


def _project(point: RenderVector, *, origin: tuple[float, float], scale: float, yaw_degrees: float = 0.0) -> tuple[float, float]:
    point = _rotate_xy(point, yaw_degrees=yaw_degrees)
    cos30 = 0.8660254038
    sin30 = 0.5
    x = origin[0] + (point.x - point.y) * cos30 * scale
    y = origin[1] + (point.x + point.y) * sin30 * scale - point.z * scale
    return x, y


def _add_vectors(left: RenderVector, right: RenderVector) -> RenderVector:
    return RenderVector(left.x + right.x, left.y + right.y, left.z + right.z)


def _draw_iso_box(
    draw: Any,
    *,
    center: RenderVector,
    size: RenderVector,
    origin: tuple[float, float],
    scale: float,
    color: tuple[int, int, int],
    outline: tuple[int, int, int],
    yaw_degrees: float = 0.0,
) -> None:
    half = RenderVector(size.x / 2, size.y / 2, size.z / 2)
    corners = {
        "lll": _add_vectors(center, RenderVector(-half.x, -half.y, -half.z)),
        "rll": _add_vectors(center, RenderVector(half.x, -half.y, -half.z)),
        "rrl": _add_vectors(center, RenderVector(half.x, half.y, -half.z)),
        "lrl": _add_vectors(center, RenderVector(-half.x, half.y, -half.z)),
        "llh": _add_vectors(center, RenderVector(-half.x, -half.y, half.z)),
        "rlh": _add_vectors(center, RenderVector(half.x, -half.y, half.z)),
        "rrh": _add_vectors(center, RenderVector(half.x, half.y, half.z)),
        "lrh": _add_vectors(center, RenderVector(-half.x, half.y, half.z)),
    }
    projected = {key: _project(value, origin=origin, scale=scale, yaw_degrees=yaw_degrees) for key, value in corners.items()}
    top = [projected["llh"], projected["rlh"], projected["rrh"], projected["lrh"]]
    left = [projected["llh"], projected["lrh"], projected["lrl"], projected["lll"]]
    right = [projected["rlh"], projected["rrh"], projected["rrl"], projected["rll"]]
    front = [projected["lrh"], projected["rrh"], projected["rrl"], projected["lrl"]]
    for polygon, fill in ((left, _shade(color, 0.58)), (right, _shade(color, 0.68)), (front, _shade(color, 0.76)), (top, color)):
        draw.polygon(polygon, fill=fill, outline=outline)


def _draw_enclosure(draw: Any, *, dimensions: RenderVector, origin: tuple[float, float], scale: float, yaw_degrees: float = 0.0, label: str = "LIVE 3D / TERMINAL") -> None:
    color = (99, 102, 241)
    outline = (196, 181, 253)
    _draw_iso_box(
        draw,
        center=RenderVector(0, 0, 0),
        size=dimensions,
        origin=origin,
        scale=scale,
        color=(42, 45, 58),
        outline=(72, 77, 95),
        yaw_degrees=yaw_degrees,
    )
    half = RenderVector(dimensions.x / 2, dimensions.y / 2, dimensions.z / 2)
    top_points = [
        _project(RenderVector(-half.x, -half.y, half.z), origin=origin, scale=scale, yaw_degrees=yaw_degrees),
        _project(RenderVector(half.x, -half.y, half.z), origin=origin, scale=scale, yaw_degrees=yaw_degrees),
        _project(RenderVector(half.x, half.y, half.z), origin=origin, scale=scale, yaw_degrees=yaw_degrees),
        _project(RenderVector(-half.x, half.y, half.z), origin=origin, scale=scale, yaw_degrees=yaw_degrees),
    ]
    draw.line(top_points + [top_points[0]], fill=outline, width=2)
    draw.text((int(origin[0] - 80), int(origin[1] - dimensions.z * scale - 125)), label, fill=color, font=_font(18, bold=True))


def _draw_scene(draw: Any, project_ir: Mapping[str, Any], *, bounds: tuple[int, int, int, int], yaw_degrees: float = 0.0, label: str = "LIVE 3D / TERMINAL") -> None:
    left, top, right, bottom = bounds
    dimensions = _dimensions(project_ir)
    placements = _placements(project_ir, dimensions)
    scene_width = right - left
    scene_height = bottom - top
    scale = min(scene_width / max(dimensions.x + dimensions.y, 1) * 0.62, scene_height / max(dimensions.z + (dimensions.x + dimensions.y) * 0.55, 1) * 0.82)
    scale = max(1.5, min(scale, 6.0))
    origin = (left + scene_width * 0.52, top + scene_height * 0.68)

    for x in range(left, right, 44):
        draw.line([(x, top), (x, bottom)], fill=(29, 33, 43), width=1)
    for y in range(top, bottom, 44):
        draw.line([(left, y), (right, y)], fill=(29, 33, 43), width=1)

    _draw_enclosure(draw, dimensions=dimensions, origin=origin, scale=scale, yaw_degrees=yaw_degrees, label=label)
    ordered = sorted(placements, key=lambda placement: placement.position.x + placement.position.y + placement.position.z)
    for placement in ordered:
        category = _category_key(placement.category)
        color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["default"])
        _draw_iso_box(
            draw,
            center=placement.position,
            size=placement.size,
            origin=origin,
            scale=scale,
            color=color,
            outline=(229, 231, 235),
            yaw_degrees=yaw_degrees,
        )
        px, py = _project(_add_vectors(placement.position, RenderVector(0, 0, placement.size.z / 2 + 4)), origin=origin, scale=scale, yaw_degrees=yaw_degrees)
        draw.text((int(px) - 18, int(py) - 18), placement.ref_des[:8], fill=(245, 247, 250), font=_font(13, bold=True))

    footer = f"{int(dimensions.x)}mm X / {int(dimensions.y)}mm Y / {int(dimensions.z)}mm Z / {len(placements)} placements"
    draw.text((left + 24, bottom - 42), footer.upper(), fill=(148, 163, 184), font=_font(15, bold=True))


def _draw_metric(draw: Any, *, x: int, y: int, width: int, label: str, value: str, color: tuple[int, int, int]) -> None:
    draw.rectangle((x, y, x + width, y + 78), fill=(20, 23, 31), outline=(43, 48, 62))
    draw.text((x + 16, y + 14), label.upper(), fill=(117, 135, 174), font=_font(12, bold=True))
    draw.text((x + 16, y + 38), value[:14], fill=color, font=_font(22, bold=True))


def _draw_components(draw: Any, components: Sequence[Any], *, x: int, y: int, width: int, max_rows: int = 8) -> None:
    draw.text((x, y), "COMPONENTS", fill=(226, 232, 240), font=_font(18, bold=True))
    y += 34
    for item in components[:max_rows]:
        component = _mapping(item)
        category = _category_key(component.get("category"))
        color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["default"])
        ref = _text(component.get("ref_des"), "PART")
        name = _text(component.get("name") or component.get("part_number"), "Unnamed component")
        draw.rectangle((x, y, x + width, y + 40), fill=(19, 22, 30), outline=(38, 43, 55))
        draw.rectangle((x, y, x + 5, y + 40), fill=color)
        draw.text((x + 14, y + 11), ref[:8], fill=(248, 250, 252), font=_font(13, bold=True))
        draw.text((x + 86, y + 11), name[:36], fill=(177, 190, 211), font=_font(13))
        y += 46


def _draw_operations(draw: Any, metadata: Mapping[str, Any], *, x: int, y: int, width: int) -> None:
    draw.text((x, y), "OPERATIONS", fill=(226, 232, 240), font=_font(18, bold=True))
    y += 34
    operations = tuple(_mapping(item) for item in _sequence(metadata.get("operation_statuses")))
    if not operations:
        operations = (
            {"label": "Hardware generation", "status": "succeeded"},
            {"label": "Product image", "status": _text(metadata.get("image_output_status"), "not_requested")},
        )
    for operation in operations[:6]:
        status = _text(operation.get("status"), "unknown")
        if status == "succeeded":
            color = (52, 211, 153)
        elif status == "failed":
            color = (251, 113, 133)
        elif status == "pending":
            color = (250, 204, 21)
        else:
            color = (100, 116, 139)
        draw.rectangle((x, y, x + width, y + 32), fill=(19, 22, 30), outline=(38, 43, 55))
        draw.ellipse((x + 12, y + 10, x + 24, y + 22), fill=color)
        draw.text((x + 36, y + 8), _text(operation.get("label") or operation.get("id"), "operation")[:28], fill=(203, 213, 225), font=_font(12, bold=True))
        draw.text((x + width - 110, y + 8), status.upper()[:13], fill=color, font=_font(12, bold=True))
        y += 38


def render_dashboard_image(
    project_ir: Mapping[str, Any],
    output_path: Path,
    *,
    subtitle: str = "",
    config: DashboardRenderConfig | None = None,
) -> Path:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError(f"Pillow is required for terminal dashboard rendering: {exc}") from exc

    cfg = config or DashboardRenderConfig()
    image = Image.new("RGB", (cfg.width, cfg.height), cfg.background)
    draw = ImageDraw.Draw(image)
    summary = _summary(project_ir, subtitle=subtitle)
    metadata = _mapping(project_ir.get("assembly_metadata"))
    components = tuple(_sequence(project_ir.get("components")))

    draw.rectangle((0, 0, cfg.width, cfg.height), fill=cfg.background)
    draw.rectangle((0, 0, cfg.width, 118), fill=(10, 12, 18))
    title_font = _font(28, bold=True)
    right_header_x = max(620, cfg.width - 430)
    title_width = max(320, right_header_x - 72)
    draw.text((36, 28), _fit_text(draw, summary.title.upper(), max_width=title_width, font=title_font), fill=(248, 250, 252), font=title_font)
    _wrap_text(draw, summary.description, x=38, y=70, width=760, fill=(148, 163, 184), font=_font(14), max_lines=2)
    draw.text((right_header_x, 34), f"PROJECT {summary.project_id or 'unsaved'}"[:44], fill=(34, 211, 238), font=_font(14, bold=True))
    draw.text((right_header_x, 62), f"{summary.provider or 'provider'} / {summary.model or 'model'}"[:44], fill=(226, 232, 240), font=_font(14, bold=True))

    side_x = int(cfg.width * 0.72)
    side_width = cfg.width - side_x - 36
    metric_y = 142
    metric_gap = 18
    metric_width = max(120, min(180, (side_x - 36 - metric_gap * 3) // 4))
    for index, (label, value, color) in enumerate(
        (
            ("Parts", str(summary.component_count), (34, 211, 238)),
            ("Nets", str(summary.net_count), (52, 211, 153)),
            ("Cost", f"${summary.estimated_cost:.2f}", (250, 204, 21)),
            ("Image", summary.image_status[:13].upper(), (167, 139, 250)),
        )
    ):
        _draw_metric(draw, x=36 + index * (metric_width + metric_gap), y=metric_y, width=metric_width, label=label, value=value, color=color)

    scene_bounds = (36, 250, side_x - 24, cfg.height - 34)
    draw.rectangle(scene_bounds, fill=(20, 21, 25), outline=(47, 51, 61), width=2)
    _draw_scene(draw, project_ir, bounds=scene_bounds, yaw_degrees=cfg.scene_yaw_degrees, label=cfg.scene_label)

    _draw_components(draw, components, x=side_x, y=150, width=side_width)
    _draw_operations(draw, metadata, x=side_x, y=560, width=side_width)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


__all__ = [
    "DashboardRenderConfig",
    "RenderPlacement",
    "RenderSummary",
    "RenderVector",
    "render_dashboard_image",
]
