"""Install the generated app icon as the Android launcher icon (idempotent).

Reads <project>/playstore_assets/icon_512.png, writes legacy mipmap icons into the
android/ container and adds android:icon to the manifest once. Called on every build
because android/ is persistent between builds.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


def apply_launcher_icon(project_dir: str, log: Callable[[str], None] = lambda m: None) -> bool:
    root = Path(project_dir)
    icon = root / "playstore_assets" / "icon_512.png"
    manifest = root / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    if not icon.is_file() or not manifest.is_file():
        return False
    res = manifest.parent / "res"
    with Image.open(icon) as src:
        base = src.convert("RGBA")
        for density, px in SIZES.items():
            folder = res / f"mipmap-{density}"
            folder.mkdir(parents=True, exist_ok=True)
            base.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher.png", optimize=True)
    text = manifest.read_text(encoding="utf-8")
    if "android:icon=" not in text:
        text = text.replace("<application ", '<application android:icon="@mipmap/ic_launcher" ', 1)
        manifest.write_text(text, encoding="utf-8")
    log("[icon] launcher icon dipasang dari playstore_assets/icon_512.png")
    return True
