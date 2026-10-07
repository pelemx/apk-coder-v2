"""
Automatic icon + in-game image generation for a freshly created web project.

Pure logic (no GUI). Called by ChatTab in a worker thread right after a project
is created from chat:

    result = generate_project_assets(project, assets_needed, log=print, description="...")

- App icon      -> <project>/playstore_assets/icon_512.png (also feeds the launcher icon)
- In-game image -> <project>/web/assets/images/<name>.png, referenced by the game as
                   assets/images/<name>.png

Every asset ends up as a real file even when the image API fails (a locally drawn
placeholder is written), so WebValidator never reports BROKEN_ASSET and the APK
always has an icon. If the API is unreachable, the remaining requests are not attempted.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

from .api_bridge import generate_image
from .icon_generator import IconGenerator
from .playstore_assets import PlaystoreAssets

STYLE = "flat design"
MAX_SIDE = {"sprite": 256, "ui": 160, "tile": 128, "background": 1024}
PROMPTS = {
    "sprite": "{p}, {style}, single subject centered, plain solid pure white background, no text, no shadow, no border",
    "ui": "{p}, {style}, game UI element, centered, plain solid pure white background, no text",
    "tile": "{p}, {style}, seamless game tile texture, top view, no text",
    "background": "{p}, {style}, game background scene, no characters, no text, full frame",
}
_DEAD_MARKERS = ("tidak bisa dihubungi", "timeout")
_VERB_PREFIX = re.compile(r"^\s*(?:tolong\s+)?(?:bikin\w*|buat\w*|generate|create|make)\s+(?:sebuah\s+|a\s+)?(?:game\s+)?", re.I)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "asset"


def _color_for(name: str) -> tuple[int, int, int]:
    h = hashlib.md5(name.encode("utf-8")).digest()
    return 60 + h[0] % 150, 60 + h[1] % 150, 60 + h[2] % 150


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # old Pillow
        return ImageFont.load_default()


# ---------------------------------------------------------------- image helpers
def remove_background(img: Image.Image, tol: int = 30) -> Image.Image:
    """Make a uniform corner-connected background transparent (best effort)."""
    rgba = img.convert("RGBA")
    rgb = img.convert("RGB")
    w, h = rgb.size
    pts = ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))
    corners = [rgb.getpixel(p) for p in pts]
    if any(max(abs(a - b) for a, b in zip(corners[0], c)) > tol for c in corners):
        return rgba                                     # background is not uniform
    marker = (254, 1, 253)
    work = rgb.copy()
    for xy in pts:
        if work.getpixel(xy) != marker:
            ImageDraw.floodfill(work, xy, marker, thresh=tol)
    original = rgba.copy()
    px, wp = rgba.load(), work.load()
    cleared = 0
    for y in range(h):
        for x in range(w):
            if wp[x, y] == marker:
                px[x, y] = (0, 0, 0, 0)
                cleared += 1
    ratio = cleared / float(w * h)
    # Implausible result (nothing cut, or almost everything cut): keep the original image.
    return original if ratio < 0.01 or ratio > 0.92 else rgba


def placeholder_image(kind: str, name: str, size: tuple[int, int] | None = None) -> Image.Image:
    color = _color_for(name)
    if kind == "background":
        w, h = size or (720, 1280)
        img = Image.new("RGB", (w, h), color)
        d = ImageDraw.Draw(img)
        dark = tuple(int(c * 0.45) for c in color)
        for y in range(h):
            t = y / float(h)
            d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(color, dark)))
        return img.convert("RGBA")
    w, h = size or (MAX_SIDE.get(kind, 128),) * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([w * 0.08, h * 0.08, w * 0.92, h * 0.92], radius=int(min(w, h) * 0.18),
                        fill=color + (255,), outline=(255, 255, 255, 230), width=max(2, w // 40))
    letter = (name[:1] or "?").upper()
    f = _font(int(min(w, h) * 0.5))
    box = d.textbbox((0, 0), letter, font=f)
    d.text(((w - (box[2] - box[0])) / 2 - box[0], (h - (box[3] - box[1])) / 2 - box[1]), letter,
           font=f, fill=(255, 255, 255, 255))
    return img


def placeholder_icon(name: str) -> Image.Image:
    base = placeholder_image("sprite", name, (512, 512))
    bg = Image.new("RGBA", (512, 512), _color_for(name + "-bg") + (255,))
    bg.alpha_composite(base)
    return bg


def save_ingame_asset(project_dir: str, kind: str, name: str, image: Image.Image) -> str:
    out_dir = Path(project_dir) / "web" / "assets" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    img = image.convert("RGBA")
    limit = MAX_SIDE.get(kind, 256)
    img.thumbnail((limit, limit), Image.LANCZOS)
    if kind in ("sprite", "ui"):
        img = remove_background(img)
    if kind == "background":
        img = img.convert("RGB")
    out = out_dir / f"{slug(name)}.png"
    img.save(out, format="PNG", optimize=True)
    return str(out)


def _clean_description(text: str) -> str:
    return _VERB_PREFIX.sub("", text or "").strip(" .!?")[:120]


# ---------------------------------------------------------------- main entry
def generate_project_assets(project: dict[str, Any], assets_needed: list[dict[str, str]],
                            log: Callable[[str], None] = lambda m: None,
                            description: str = "",
                            generate: Callable[[str], Image.Image] = generate_image) -> dict[str, Any]:
    wd = project["working_dir"]
    result: dict[str, Any] = {"icon": None, "ingame": [], "errors": [], "placeholders": []}
    api_dead = False
    pa = PlaystoreAssets(wd)

    # 1) app icon ---------------------------------------------------------
    prompts = IconGenerator(project).build_prompts(description=_clean_description(description), style=STYLE)
    log("Generate icon app ...")
    try:
        result["icon"] = pa.save_app_icon(generate(prompts["icon"]))
        log("Icon app selesai.")
    except Exception as exc:  # noqa: BLE001 - network/API/PIL errors all degrade to a local icon
        msg = str(exc)
        api_dead = any(m in msg.lower() for m in _DEAD_MARKERS)
        result["errors"].append(f"icon: {msg}")
        log(f"Icon dari API gagal ({msg[:120]}). Memakai icon sederhana buatan lokal.")
        result["icon"] = pa.save_app_icon(placeholder_icon(project.get("name", "app")))
        result["placeholders"].append("icon")

    # 2) in-game images -----------------------------------------------------
    for i, item in enumerate(assets_needed, 1):
        kind, name, base_prompt = item["kind"], slug(item["name"]), item["prompt"]
        label = f"{kind} '{name}' ({i}/{len(assets_needed)})"
        if api_dead:
            path = save_ingame_asset(wd, kind, name, placeholder_image(kind, name))
            result["ingame"].append(path)
            result["placeholders"].append(name)
            log(f"{label}: server gambar tidak terjangkau, pakai placeholder.")
            continue
        log(f"Generate {label} ...")
        prompt = PROMPTS.get(kind, PROMPTS["sprite"]).format(p=base_prompt, style=STYLE)
        try:
            path = save_ingame_asset(wd, kind, name, generate(prompt))
            log(f"{label} selesai.")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            api_dead = any(m in msg.lower() for m in _DEAD_MARKERS)
            result["errors"].append(f"{name}: {msg}")
            path = save_ingame_asset(wd, kind, name, placeholder_image(kind, name))
            result["placeholders"].append(name)
            log(f"{label} gagal ({msg[:100]}); pakai placeholder.")
        result["ingame"].append(path)
    return result
