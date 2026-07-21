#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.prefix).resolve() != (REPO_ROOT / ".venv").resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(REPO_ROOT))

from blueprint_core.image_providers import build_image_provider
from blueprint_core.user_integrations import UserIntegrationStore, apply_user_integrations_to_environment


def _minimal_ir() -> Any:
    vector = lambda x, y, z: SimpleNamespace(x_mm=x, y_mm=y, z_mm=z)
    return SimpleNamespace(
        assembly_metadata={"render_dimensions": {"x_mm": 120, "y_mm": 72, "z_mm": 28}},
        overview=SimpleNamespace(
            title="Image Provider Smoke Test Device",
            description="Compact handheld electronics enclosure with a small display, one button, and USB-C power.",
        ),
        mechanical=SimpleNamespace(
            enclosure_type="compact handheld enclosure",
            mounting_guidance="display and button on the top face; USB-C on the side wall",
            render_dimensions=vector(120, 72, 28),
            component_placements=[
                SimpleNamespace(
                    ref_des="U1",
                    label="controller board",
                    category="controller",
                    layer="bottom_shell",
                    position=vector(48, 36, 8),
                    size=vector(46, 28, 4),
                    mounting_face="bottom_floor",
                    notes="mounted on standoffs",
                ),
                SimpleNamespace(
                    ref_des="DS1",
                    label="display",
                    category="display",
                    layer="lid",
                    position=vector(42, 28, 28),
                    size=vector(38, 18, 3),
                    mounting_face="top_lid",
                    notes="visible through lid cutout",
                ),
                SimpleNamespace(
                    ref_des="J1",
                    label="USB-C connector",
                    category="connector",
                    layer="side_wall",
                    position=vector(108, 36, 10),
                    size=vector(9, 7, 4),
                    mounting_face="right_wall",
                    notes="flush with side cutout",
                ),
            ],
        ),
        components=[
            SimpleNamespace(ref_des="U1", name="Controller board", part_number="MCU-DEV", category="controller", quantity=1),
            SimpleNamespace(ref_des="DS1", name="OLED display", part_number="OLED-12864", category="display", quantity=1),
            SimpleNamespace(ref_des="SW1", name="Tactile button", part_number="BTN-6MM", category="control", quantity=1),
            SimpleNamespace(ref_des="J1", name="USB-C power connector", part_number="USB-C", category="connector", quantity=1),
        ],
        nets=[],
        constraints=["Low-voltage bench prototype", "Show real enclosure, display, controls, and USB-C port"],
        fabrication_notes=["Smoke test render only; not a manufacturing release."],
    )


def _decode_data_url(value: str) -> Tuple[bytes, str]:
    if value.startswith(("http://", "https://")):
        request = urllib.request.Request(value, headers={"User-Agent": "Forma-OSS/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read(), response.headers.get_content_type() or "image/png"

    if "," not in value:
        return base64.b64decode(value), "image/png"

    header, data = value.split(",", 1)
    content_type = "image/png"
    if header.startswith("data:") and ";base64" in header:
        content_type = header.removeprefix("data:").split(";", 1)[0] or content_type
    return base64.b64decode(data), content_type


def _extension_for_content_type(content_type: str) -> str:
    normalized = content_type.lower().split(";", 1)[0].strip()
    if normalized == "image/jpeg":
        return ".jpg"
    if normalized == "image/webp":
        return ".webp"
    if normalized == "image/svg+xml":
        return ".svg"
    return ".png"


def _output_path(path: Path, content_type: str) -> Path:
    if path.suffix:
        return path
    return path.with_suffix(_extension_for_content_type(content_type))


def _redact_debug(debug: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in debug.items():
        if any(token in key.lower() for token in ("key", "token", "secret", "authorization")):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _load_saved_config(user_id: Optional[str]) -> None:
    if user_id:
        apply_user_integrations_to_environment(UserIntegrationStore.for_user(user_id))
    else:
        apply_user_integrations_to_environment()


def main() -> int:
    parser = argparse.ArgumentParser(description="Make one direct image-provider request without running the hardware pipeline.")
    parser.add_argument("--user-id", default=os.getenv("BLUEPRINT_TEST_USER_ID") or os.getenv("BLUEPRINT_USER_ID"), help="Clerk user id whose saved BYOK settings should be loaded.")
    parser.add_argument("--prompt", default="A compact handheld electronics prototype with display, one button, USB-C power, and a simple matte enclosure on a white background.")
    parser.add_argument("--output", default=".tmp/image-provider-smoke", help="Where to save the generated image. Extension is inferred when omitted.")
    parser.add_argument("--config-only", action="store_true", help="Only load config and print provider debug; do not call the provider.")
    args = parser.parse_args()

    _load_saved_config(args.user_id)
    provider = build_image_provider(force_enabled=True)
    debug = _redact_debug(provider.get_debug_config())
    print(json.dumps({"image_provider": debug}, indent=2, sort_keys=True))

    if not debug.get("configured"):
        print(f"Image provider is not configured: {debug.get('reason') or 'unknown reason'}", file=sys.stderr)
        return 2

    if args.config_only:
        print("Config check passed; provider is configured.")
        return 0

    try:
        image = provider.generate_project_image(args.prompt, _minimal_ir())
    except Exception as exc:
        print(f"Image provider smoke test failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    if not image or not image.data_url:
        print("Image provider smoke test failed: provider returned no image data.", file=sys.stderr)
        return 1

    image_bytes, content_type = _decode_data_url(image.data_url)
    output_path = _output_path(Path(args.output), content_type)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "bytes": len(image_bytes),
                "content_type": content_type,
                "provider": image.provider,
                "model": image.model,
                "size": image.size,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
