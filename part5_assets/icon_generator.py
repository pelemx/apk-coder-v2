"""
Icon / asset prompt generation from project data (spec 5.4).

Builds prompts from: game name, description, genre, dominant colors found in
the pygame source, and a visual style. No GUI code here (see assets_panel.py).
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .api_bridge import ImageAPIError, generate_image, generate_image_thread  # noqa: F401
from .playstore_assets import PlaystoreAssets

STYLES = ["flat design", "cartoon", "pixel art", "3D render", "minimal", "hand-drawn", "neon"]
GENRES = ["puzzle", "arcade", "casual", "action", "platformer", "educational", "racing", "card"]

EXCLUDES = {".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist",
            "cache", ".juprisx", ".buildozer", "bin", "playstore_assets"}

# Reference palette used to give colors human names for the prompt.
NAMED_COLORS = {
    "red": (231, 76, 60), "orange": (230, 126, 34), "yellow": (241, 196, 15),
    "green": (46, 204, 113), "teal": (26, 188, 156), "cyan": (0, 200, 220),
    "blue": (52, 152, 219), "navy": (30, 50, 120), "purple": (155, 89, 182),
    "pink": (255, 105, 180), "brown": (139, 90, 43),
}


def _is_neutral(rgb: tuple[int, int, int]) -> bool:
    """Near-black, near-white or grey colors say nothing about the game's identity."""
    return (max(rgb) - min(rgb)) < 28


def _rgb_from_node(node: ast.AST) -> tuple[int, int, int] | None:
    if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) in (3, 4):
        vals = []
        for e in node.elts[:3]:
            if isinstance(e, ast.Constant) and isinstance(e.value, int) and 0 <= e.value <= 255:
                vals.append(e.value)
            else:
                return None
        return tuple(vals)  # type: ignore[return-value]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        m = re.fullmatch(r"#([0-9a-fA-F]{6})", node.value)
        if m:
            h = m.group(1)
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return None


_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")


def _rgbs_from_text(text: str):
    """Color literals in CSS/JS/HTML: #rgb, #rrggbb, rgb()/rgba()."""
    for m in _HEX_RE.finditer(text):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        yield int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    for m in _RGB_RE.finditer(text):
        r, g, b = (int(x) for x in m.groups())
        if max(r, g, b) <= 255:
            yield r, g, b


def name_color(rgb: tuple[int, int, int]) -> str:
    return min(NAMED_COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(NAMED_COLORS[n], rgb)))


def extract_dominant_colors(project_dir: str, top: int = 3) -> list[dict[str, Any]]:
    """Most used non-neutral RGB / hex literals in the project's .py files.
    Returns [{'rgb': (r,g,b), 'name': 'blue', 'count': n}, ...]."""
    root = Path(project_dir)
    counter: Counter = Counter()
    if not root.is_dir():
        return []
    for path in root.rglob("*.py"):
        if any(part in EXCLUDES for part in path.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            rgb = _rgb_from_node(node)
            if rgb and not _is_neutral(rgb):
                counter[rgb] += 1

    # HTML/JS/CSS web projects: scan web/ (or the project root when there is no web/).
    web = root / "web"
    base = web if web.is_dir() else root
    for path in base.rglob("*"):
        if path.suffix.lower() not in (".css", ".js", ".html") or not path.is_file():
            continue
        if any(part in EXCLUDES for part in path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for rgb in _rgbs_from_text(text):
            if not _is_neutral(rgb):
                counter[rgb] += 1

    # Merge shades that map to the same color name so "top 3" gives distinct hues.
    by_name: Counter = Counter()
    representative: dict[str, tuple[int, int, int]] = {}
    for rgb, n in counter.items():
        name = name_color(rgb)
        by_name[name] += n
        if name not in representative or counter[rgb] > counter[representative[name]]:
            representative[name] = rgb
    return [{"rgb": representative[n], "name": n, "count": c}
            for n, c in by_name.most_common(top)]


class IconGenerator:
    """Builds prompts from project data and (optionally) calls the image API."""

    def __init__(self, project: dict | None = None):
        self.project = project or {}

    @property
    def working_dir(self) -> str:
        return self.project.get("working_dir", "")

    def project_info(self, description: str = "", genre: str = "") -> dict[str, str]:
        colors = extract_dominant_colors(self.working_dir) if self.working_dir else []
        return {
            "name": self.project.get("name", "My Game"),
            "description": description,
            "genre": genre,
            "color": " and ".join(c["name"] for c in colors[:2]),
        }

    def build_prompts(self, description: str = "", genre: str = "",
                      style: str = "flat design", ratio: str = "9:16") -> dict[str, str]:
        info = self.project_info(description, genre)
        pa = PlaystoreAssets(self.working_dir or ".")
        args = (info["name"], info["description"], info["genre"], info["color"], style)
        return {
            "icon": pa.generate_icon_prompt(*args),
            "feature_graphic": pa.generate_feature_prompt(*args),
            "screenshot": pa.generate_screenshot_prompt(*args, ratio=ratio),
        }

    def generate(self, prompt: str):
        """Blocking call -> PIL.Image. Raises ImageAPIError."""
        return generate_image(prompt)
