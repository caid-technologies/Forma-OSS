"""Deterministic screenshot-style project views used by PDF exports."""

from __future__ import annotations

import io
import math
import textwrap
from functools import lru_cache
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont


VIEW_NAMES = ("INFO", "BOM", "MECH", "WIRE", "DOCS")
VIEW_SIZE = (1600, 1000)

BG = "#090d14"
PANEL = "#101823"
PANEL_ALT = "#0c131d"
BORDER = "#26364a"
TEXT = "#edf4fb"
MUTED = "#8da0b5"
CYAN = "#22d3ee"
CYAN_DARK = "#0e7490"
YELLOW = "#facc15"
GREEN = "#34d399"
RED = "#fb7185"
BLUE = "#60a5fa"
PURPLE = "#c084fc"
NET_COLORS = (CYAN, YELLOW, GREEN, BLUE, PURPLE, RED)


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any, fallback: str = "") -> str:
    value = str(value or " ").strip()
    return value if value else fallback


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else ("DejaVuSans.ttf",)
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str = PANEL, outline: str = BORDER, radius: int = 16, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _fit_lines(draw: ImageDraw.ImageDraw, value: Any, *, font: ImageFont.ImageFont, width: int, max_lines: int) -> list[str]:
    text = " ".join(_text(value).split())
    if not text:
        return []
    average = max(1, int(draw.textlength("ABCDEFGHIJKLMNOPQRSTUVWXYZ", font=font) / 26))
    lines = textwrap.wrap(text, width=max(8, width // average), break_long_words=True)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "..."
    return lines


def _multiline(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: Any, *, font: ImageFont.ImageFont, fill: str = TEXT, width: int, max_lines: int = 4, spacing: int = 8) -> int:
    lines = _fit_lines(draw, value, font=font, width=width, max_lines=max_lines)
    if not lines:
        return xy[1]
    draw.multiline_text(xy, "\n".join(lines), font=font, fill=fill, spacing=spacing)
    line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
    return xy[1] + (len(lines) * line_height) + ((len(lines) - 1) * spacing)


def _base(project: dict[str, Any], active: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", VIEW_SIZE, BG)
    draw = ImageDraw.Draw(image)
    overview = _mapping(project.get("overview"))
    title = _text(overview.get("title"), "Untitled Forma Project")

    draw.text((54, 35), "FORMA", font=_font(19, True), fill=CYAN)
    draw.text((54, 67), title, font=_font(28, True), fill=TEXT)
    draw.text((1545, 47), "PROJECT CAPTURE", font=_font(13, True), fill=MUTED, anchor="ra")
    draw.text((1545, 76), "AI-assisted prototype", font=_font(12), fill="#60758c", anchor="ra")
    draw.line((54, 112, 1546, 112), fill=BORDER, width=2)

    x = 54
    for name in VIEW_NAMES:
        tab_width = 126
        is_active = name == active
        if is_active:
            draw.rounded_rectangle((x, 126, x + tab_width, 172), radius=11, fill="#12303b", outline=CYAN_DARK, width=2)
        draw.text((x + tab_width // 2, 149), name, font=_font(14, True), fill=CYAN if is_active else MUTED, anchor="mm")
        x += tab_width + 10
    return image, draw


def _metric(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, accent: str = CYAN) -> None:
    _rounded(draw, box)
    x1, y1, _x2, _y2 = box
    draw.rectangle((x1, y1, x1 + 5, _y2), fill=accent)
    draw.text((x1 + 25, y1 + 20), label.upper(), font=_font(12, True), fill=MUTED)
    draw.text((x1 + 25, y1 + 55), value, font=_font(26, True), fill=TEXT)


def _info_view(project: dict[str, Any]) -> Image.Image:
    image, draw = _base(project, "INFO")
    overview = _mapping(project.get("overview"))
    requirements = _mapping(project.get("requirements"))
    validation = _mapping(project.get("validation"))
    components = _items(project.get("components"))
    nets = _items(project.get("nets"))
    critical_count = len(_items(validation.get("critical")))
    warning_count = len(_items(validation.get("warning")))

    _rounded(draw, (54, 194, 1546, 365), fill=PANEL_ALT)
    draw.text((82, 220), _text(overview.get("category"), "HARDWARE PROJECT").upper(), font=_font(13, True), fill=CYAN)
    draw.text((82, 253), _text(overview.get("title"), "Untitled Forma Project"), font=_font(34, True), fill=TEXT)
    _multiline(draw, (82, 302), overview.get("description"), font=_font(17), fill=MUTED, width=1370, max_lines=2)

    _metric(draw, (54, 389, 330, 508), "Estimated BOM", f"${_number(overview.get('estimated_cost')):,.2f}", YELLOW)
    _metric(draw, (350, 389, 626, 508), "Components", str(len(components)), CYAN)
    _metric(draw, (646, 389, 922, 508), "Electrical nets", str(len(nets)), BLUE)
    _metric(draw, (942, 389, 1218, 508), "Peak current", f"{_number(project.get('estimated_current_draw_ma')):,.0f} mA", PURPLE)
    status = "BLOCKED" if critical_count else ("REVIEW" if warning_count else "PASS")
    _metric(draw, (1238, 389, 1546, 508), "Validation", status, RED if critical_count else YELLOW if warning_count else GREEN)

    _rounded(draw, (54, 532, 982, 946))
    draw.text((82, 558), "REQUIREMENTS", font=_font(15, True), fill=CYAN)
    power = _text(requirements.get("power_needs"), "Power requirements not supplied")
    voltage = requirements.get("operating_voltage")
    if voltage is not None:
        power += f"  /  {_number(voltage):g} V logic"
    power_bottom = _multiline(
        draw,
        (82, 591),
        power,
        font=_font(18, True),
        fill=TEXT,
        width=820,
        max_lines=2,
        spacing=5,
    )
    y = power_bottom + 24
    requirement_items = _items(requirements.get("requirements")) + _items(requirements.get("physical_constraints"))
    for item in requirement_items[:8]:
        draw.ellipse((84, y + 7, 92, y + 15), fill=CYAN)
        y = _multiline(draw, (106, y), item, font=_font(15), fill=MUTED, width=820, max_lines=2) + 17

    _rounded(draw, (1004, 532, 1546, 946))
    draw.text((1032, 558), "SAFETY & OPEN ITEMS", font=_font(15, True), fill=YELLOW)
    safety_items = _items(requirements.get("safety_notes")) + [f"Open: {_text(item)}" for item in _items(requirements.get("missing_info"))]
    if not safety_items:
        safety_items = ["No additional safety notes were reported."]
    y = 600
    for item in safety_items[:7]:
        _rounded(draw, (1030, y, 1520, min(y + 64, 920)), fill="#171a1c", outline="#4b4521", radius=10, width=1)
        _multiline(draw, (1048, y + 14), item, font=_font(14), fill="#d8cf9e", width=450, max_lines=2, spacing=5)
        y += 76
        if y > 900:
            break
    return image


def _bom_view(project: dict[str, Any]) -> Image.Image:
    image, draw = _base(project, "BOM")
    components = [_mapping(item) for item in _items(project.get("components"))]
    total = sum(_number(item.get("unit_price")) * max(1, int(_number(item.get("quantity"), 1))) for item in components)

    draw.text((54, 206), "BILL OF MATERIALS", font=_font(24, True), fill=TEXT)
    draw.text((1546, 212), f"{len(components)} line items   /   ${total:,.2f} estimated", font=_font(15, True), fill=YELLOW, anchor="ra")
    _rounded(draw, (54, 250, 1546, 925), radius=12)
    columns = ((76, "REF"), (174, "PART / DESCRIPTION"), (790, "CATEGORY"), (1060, "QTY"), (1160, "UNIT"), (1320, "EXTENDED"))
    draw.rectangle((55, 251, 1545, 302), fill="#142131")
    for x, label in columns:
        draw.text((x, 268), label, font=_font(12, True), fill=CYAN)
    row_y = 303
    row_height = 57
    for index, component in enumerate(components[:10]):
        if index % 2:
            draw.rectangle((56, row_y, 1544, row_y + row_height), fill="#0d151f")
        ref = _text(component.get("ref_des"), "-")
        part = _text(component.get("part_number"), "Unspecified")
        name = _text(component.get("name"), "Unnamed component")
        category = _text(component.get("category"), "Other")
        quantity = max(1, int(_number(component.get("quantity"), 1)))
        price = _number(component.get("unit_price"))
        draw.text((76, row_y + 18), ref, font=_font(14, True), fill=CYAN)
        draw.text((174, row_y + 10), part, font=_font(14, True), fill=TEXT)
        draw.text((174, row_y + 32), name[:68], font=_font(12), fill=MUTED)
        draw.text((790, row_y + 19), category[:26], font=_font(13), fill=MUTED)
        draw.text((1076, row_y + 19), str(quantity), font=_font(13, True), fill=TEXT)
        draw.text((1160, row_y + 19), f"${price:,.2f}", font=_font(13), fill=TEXT)
        draw.text((1320, row_y + 19), f"${price * quantity:,.2f}", font=_font(13, True), fill=YELLOW)
        row_y += row_height
    if len(components) > 10:
        draw.text((76, 886), f"+ {len(components) - 10} additional line items in Hardware IR", font=_font(13), fill=MUTED)
    draw.text((1540, 950), "Pricing and availability require supplier verification.", font=_font(12), fill="#66788b", anchor="ra")
    return image


def _placement_values(project: dict[str, Any]) -> list[dict[str, Any]]:
    mechanical = _mapping(project.get("mechanical"))
    placements = [_mapping(item) for item in _items(mechanical.get("component_placements"))]
    if placements:
        return placements
    generated = []
    for index, item in enumerate(_items(project.get("components"))[:12]):
        component = _mapping(item)
        column = index % 4
        row = index // 4
        generated.append({
            "ref_des": component.get("ref_des"),
            "label": component.get("name"),
            "category": component.get("category"),
            "position": {"x_mm": (column - 1.5) * 28, "y_mm": (row - 1) * 23, "z_mm": 0},
            "size": {"x_mm": 20, "y_mm": 14, "z_mm": 7},
        })
    return generated


def _mech_view(project: dict[str, Any]) -> Image.Image:
    image, draw = _base(project, "MECH")
    mechanical = _mapping(project.get("mechanical"))
    placements = _placement_values(project)
    canvas = (54, 194, 1080, 946)
    _rounded(draw, canvas, fill="#081019")
    draw.text((82, 220), "MECHANICAL PLACEMENT", font=_font(15, True), fill=CYAN)
    draw.text((1050, 220), "TOP / ISOMETRIC PLAN", font=_font(11, True), fill=MUTED, anchor="ra")

    center_x, center_y = 565, 575
    draw.polygon(((225, 680), (565, 400), (910, 650), (565, 865)), fill="#111c29", outline="#3a5069")
    for offset in range(-240, 241, 80):
        draw.line((center_x + offset, 410, center_x + offset, 855), fill="#17283a", width=1)
        draw.line((230, center_y + offset // 2, 905, center_y + offset // 2), fill="#17283a", width=1)

    positions = []
    for placement in placements:
        position = _mapping(placement.get("position"))
        positions.append((_number(position.get("x_mm")), _number(position.get("y_mm"))))
    max_extent = max([abs(value) for pair in positions for value in pair] or [50.0]) or 50.0
    scale = min(5.2, 285 / max_extent)
    for index, placement in enumerate(placements[:14]):
        position = _mapping(placement.get("position"))
        size = _mapping(placement.get("size"))
        px = center_x + int((_number(position.get("x_mm")) - _number(position.get("y_mm")) * 0.45) * scale)
        py = center_y + int((_number(position.get("y_mm")) * 0.48 + _number(position.get("x_mm")) * 0.08) * scale)
        width = max(54, min(150, int(_number(size.get("x_mm"), 18) * scale * 0.55)))
        height = max(34, min(90, int(_number(size.get("y_mm"), 12) * scale * 0.45)))
        color = NET_COLORS[index % len(NET_COLORS)]
        draw.rounded_rectangle((px - width // 2 + 8, py - height // 2 - 9, px + width // 2 + 8, py + height // 2 - 9), radius=7, fill="#182536", outline=color, width=2)
        draw.line((px - width // 2, py + height // 2, px - width // 2 + 8, py + height // 2 - 9), fill=color, width=2)
        label = _text(placement.get("ref_des"), f"P{index + 1}")
        draw.text((px + 8, py - 9), label, font=_font(12, True), fill=TEXT, anchor="mm")

    _rounded(draw, (1104, 194, 1546, 946))
    draw.text((1132, 220), "FABRICATION NOTES", font=_font(15, True), fill=CYAN)
    draw.text((1132, 260), _text(mechanical.get("enclosure_type"), "Enclosure not specified"), font=_font(20, True), fill=TEXT)
    draw.text((1132, 296), _text(mechanical.get("manufacturability_rating"), "Unrated").upper(), font=_font(12, True), fill=YELLOW)
    y = _multiline(draw, (1132, 338), mechanical.get("mounting_guidance"), font=_font(14), fill=MUTED, width=380, max_lines=7) + 28
    for note in _items(mechanical.get("fabrication_details"))[:7]:
        draw.rectangle((1134, y + 6, 1141, y + 13), fill=CYAN)
        y = _multiline(draw, (1156, y), note, font=_font(13), fill=MUTED, width=350, max_lines=3, spacing=5) + 18
        if y > 900:
            break
    return image


def _wire_view(project: dict[str, Any]) -> Image.Image:
    image, draw = _base(project, "WIRE")
    components = [_mapping(item) for item in _items(project.get("components"))]
    nets = [_mapping(item) for item in _items(project.get("nets"))]
    diagram_box = (54, 194, 1110, 946)
    _rounded(draw, diagram_box, fill="#081019")
    draw.text((82, 220), "ELECTRICAL NET MAP", font=_font(15, True), fill=CYAN)

    visible_components = components[:12]
    centers: dict[str, tuple[int, int]] = {}
    count = max(1, len(visible_components))
    for index, component in enumerate(visible_components):
        angle = (-math.pi / 2) + (index * 2 * math.pi / count)
        cx = 580 + int(math.cos(angle) * 360)
        cy = 570 + int(math.sin(angle) * 255)
        centers[_text(component.get("ref_des"), f"C{index + 1}")] = (cx, cy)

    for net_index, net in enumerate(nets[:12]):
        color = NET_COLORS[net_index % len(NET_COLORS)]
        points = []
        for pin_value in _items(net.get("pins")):
            pin = _mapping(pin_value)
            center = centers.get(_text(pin.get("ref_des")))
            if center:
                points.append(center)
        if len(points) >= 2:
            for point in points[1:]:
                draw.line((*points[0], *point), fill=color, width=5)
        elif len(points) == 1:
            draw.line((*points[0], points[0][0] + 55, points[0][1]), fill=color, width=5)

    for index, component in enumerate(visible_components):
        ref = _text(component.get("ref_des"), f"C{index + 1}")
        cx, cy = centers[ref]
        _rounded(draw, (cx - 82, cy - 37, cx + 82, cy + 37), fill="#142131", outline="#3d5874", radius=10, width=2)
        draw.text((cx, cy - 11), ref, font=_font(14, True), fill=CYAN, anchor="mm")
        draw.text((cx, cy + 14), _text(component.get("name"), "Component")[:22], font=_font(10), fill=TEXT, anchor="mm")

    _rounded(draw, (1134, 194, 1546, 946))
    draw.text((1162, 220), "NETS", font=_font(15, True), fill=CYAN)
    y = 264
    for index, net in enumerate(nets[:10]):
        color = NET_COLORS[index % len(NET_COLORS)]
        pins = []
        for pin_value in _items(net.get("pins")):
            pin = _mapping(pin_value)
            pins.append(f"{_text(pin.get('ref_des'))}.{_text(pin.get('pin_id'))}")
        _rounded(draw, (1160, y, 1520, y + 58), fill="#0d151f", outline="#23364b", radius=9, width=1)
        draw.rectangle((1160, y, 1166, y + 58), fill=color)
        draw.text((1182, y + 10), _text(net.get("name"), _text(net.get("net_id"), "Unnamed net"))[:35], font=_font(13, True), fill=TEXT)
        draw.text((1182, y + 34), "  /  ".join(pins)[:48] or _text(net.get("net_type"), "No pins"), font=_font(10), fill=MUTED)
        y += 67
    if not nets:
        draw.text((1162, 272), "No electrical nets supplied.", font=_font(14), fill=MUTED)
    return image


def _docs_view(project: dict[str, Any]) -> Image.Image:
    image, draw = _base(project, "DOCS")
    assembly = [_mapping(item) for item in _items(project.get("assembly"))]
    validation = _mapping(project.get("validation"))
    issues = [*_items(validation.get("critical")), *_items(validation.get("warning")), *_items(validation.get("info"))]

    _rounded(draw, (54, 194, 1026, 946))
    draw.text((82, 220), "ASSEMBLY PROCEDURE", font=_font(15, True), fill=CYAN)
    y = 266
    for index, step in enumerate(assembly[:6], start=1):
        height = 96
        danger = bool(step.get("danger_flag"))
        _rounded(draw, (82, y, 998, y + height), fill="#0d151f", outline="#5a3038" if danger else BORDER, radius=11, width=2)
        draw.ellipse((102, y + 18, 150, y + 66), fill="#12303b", outline=CYAN_DARK, width=2)
        draw.text((126, y + 42), str(step.get("step_num") or index), font=_font(16, True), fill=CYAN, anchor="mm")
        draw.text((168, y + 17), _text(step.get("title"), f"Step {index}")[:72], font=_font(15, True), fill=TEXT)
        _multiline(draw, (168, y + 47), step.get("description"), font=_font(12), fill=MUTED, width=790, max_lines=2, spacing=4)
        if danger:
            draw.text((968, y + 19), "WARNING", font=_font(10, True), fill=RED, anchor="ra")
        y += height + 14
        if y > 920:
            break
    if not assembly:
        draw.text((82, 276), "No assembly steps supplied.", font=_font(14), fill=MUTED)

    _rounded(draw, (1050, 194, 1546, 946))
    draw.text((1078, 220), "VALIDATION NOTES", font=_font(15, True), fill=CYAN)
    if not issues:
        draw.text((1078, 266), "PASS", font=_font(26, True), fill=GREEN)
        draw.text((1078, 310), "No validation findings were reported.", font=_font(14), fill=MUTED)
    y = 266
    for issue_value in issues[:7]:
        issue = _mapping(issue_value)
        severity = _text(issue.get("severity"), "INFO").upper()
        accent = RED if severity == "CRITICAL" else YELLOW if severity == "WARNING" else BLUE
        draw.text((1078, y), severity, font=_font(11, True), fill=accent)
        draw.text((1168, y), _text(issue.get("category"), "Validation note")[:34], font=_font(12, True), fill=TEXT)
        y = _multiline(draw, (1078, y + 25), issue.get("description"), font=_font(12), fill=MUTED, width=430, max_lines=3, spacing=4) + 24
        draw.line((1078, y - 10, 1518, y - 10), fill=BORDER, width=1)
        if y > 900:
            break
    draw.text((1518, 916), "Verify all ratings before fabrication or power-up.", font=_font(10), fill="#66788b", anchor="ra")
    return image


def render_project_view_images(project_ir: Any) -> list[tuple[str, Image.Image]]:
    """Render the five Forma workspace views as screenshot-like RGB images."""
    project = _mapping(project_ir)
    return [
        ("info", _info_view(project)),
        ("bom", _bom_view(project)),
        ("mech", _mech_view(project)),
        ("wire", _wire_view(project)),
        ("docs", _docs_view(project)),
    ]


def render_project_view_screenshots(project_ir: Any) -> list[tuple[str, bytes]]:
    """Return PNG screenshots for inspection, tests, or alternate delivery."""
    screenshots: list[tuple[str, bytes]] = []
    for name, image in render_project_view_images(project_ir):
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        screenshots.append((name, output.getvalue()))
    return screenshots


def render_project_screenshot_pdf(project_ir: Any) -> bytes:
    """Assemble one landscape PDF page per Forma workspace screenshot."""
    pages = [image for _name, image in render_project_view_images(project_ir)]
    output = io.BytesIO()
    pages[0].save(
        output,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=144.0,
        quality=88,
        title=_text(_mapping(_mapping(project_ir).get("overview")).get("title"), "Forma Project Report"),
        author="Forma",
        subject="INFO, BOM, MECH, WIRE, and DOCS workspace captures",
    )
    return output.getvalue()


__all__ = [
    "VIEW_NAMES",
    "VIEW_SIZE",
    "render_project_screenshot_pdf",
    "render_project_view_images",
    "render_project_view_screenshots",
]
