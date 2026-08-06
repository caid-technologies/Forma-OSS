from __future__ import annotations

import shutil
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
IMAGE_PATH_PATTERN = re.compile(r"((?:~|/|\.{1,2}/)?[A-Za-z0-9_@%+=:,./-]+\.(?:png|jpg|jpeg|webp|gif|bmp))", re.IGNORECASE)


@dataclass(frozen=True)
class TerminalImageRenderConfig:
    width: Optional[int] = None
    max_height: int = 40
    background_rgb: tuple[int, int, int] = (0, 0, 0)


class TerminalImageRenderer:
    def __init__(self, config: TerminalImageRenderConfig | None = None) -> None:
        self.config = config or TerminalImageRenderConfig()

    def render(self, path: Path) -> str:
        try:
            from PIL import Image
        except Exception as exc:
            return f"[terminal-image] Pillow is required to render images: {exc}"

        resolved = path.expanduser()
        if not resolved.exists():
            return f"[terminal-image] missing image: {resolved}"

        try:
            with Image.open(resolved) as opened:
                image = opened.convert("RGBA")
        except Exception as exc:
            return f"[terminal-image] unreadable image={resolved} error={exc}"

        image = self._composite_alpha(image)
        image = self._resize(image)
        return self._render_half_blocks(image)

    def _composite_alpha(self, image: Any) -> Any:
        from PIL import Image

        background = Image.new("RGBA", image.size, (*self.config.background_rgb, 255))
        background.alpha_composite(image)
        return background.convert("RGB")

    def _resize(self, image: Any) -> Any:
        terminal_width = shutil.get_terminal_size((100, 40)).columns
        target_width = self.config.width or min(80, terminal_width)
        target_width = max(1, min(target_width, terminal_width))
        source_width, source_height = image.size
        if source_width <= 0 or source_height <= 0:
            return image

        pixel_height_limit = max(1, self.config.max_height * 2)
        scale = min(target_width / source_width, pixel_height_limit / source_height, 1.0)
        resized_width = max(1, int(source_width * scale))
        resized_height = max(1, int(source_height * scale))
        return image.resize((resized_width, resized_height))

    def _render_half_blocks(self, image: Any) -> str:
        reset = "\033[0m"
        lines: list[str] = []
        width, height = image.size
        for y in range(0, height, 2):
            cells: list[str] = []
            for x in range(width):
                upper = image.getpixel((x, y))
                lower = image.getpixel((x, min(y + 1, height - 1)))
                cells.append(
                    f"\033[38;2;{upper[0]};{upper[1]};{upper[2]}m"
                    f"\033[48;2;{lower[0]};{lower[1]};{lower[2]}m"
                    "▀"
                )
            lines.append("".join(cells) + reset)
        return "\n".join(lines)


def is_image_path(value: str) -> bool:
    if value.startswith("data:image/"):
        return False
    if value.startswith(("http://", "https://")):
        return False
    if any(character.isspace() for character in value.strip()):
        return False
    return Path(value.split("?", 1)[0]).suffix.lower() in IMAGE_EXTENSIONS


def candidate_image_strings(value: str) -> tuple[str, ...]:
    stripped = value.strip()
    if is_image_path(stripped):
        return (stripped,)
    without_urls = re.sub(r"https?://\S+", "", value)
    candidates: list[str] = []
    for match in IMAGE_PATH_PATTERN.finditer(without_urls):
        candidate = match.group(1).rstrip(".,;:)]}'\"")
        if is_image_path(candidate):
            candidates.append(candidate)
    return tuple(candidates)


def extract_image_paths(value: Any, *, base_dir: Path | None = None) -> tuple[Path, ...]:
    paths: list[Path] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested)
            return
        if not isinstance(item, str):
            return
        for candidate in candidate_image_strings(item):
            path = Path(candidate).expanduser()
            if not path.is_absolute() and base_dir is not None:
                path = base_dir / path
            paths.append(path)

    visit(value)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def render_images(paths: Iterable[Path], config: TerminalImageRenderConfig | None = None) -> str:
    renderer = TerminalImageRenderer(config)
    sections: list[str] = []
    for path in paths:
        sections.append(f"[terminal-image] {path}")
        sections.append(renderer.render(path))
    return "\n".join(sections)


__all__ = [
    "IMAGE_EXTENSIONS",
    "TerminalImageRenderConfig",
    "TerminalImageRenderer",
    "candidate_image_strings",
    "extract_image_paths",
    "is_image_path",
    "render_images",
]
