"""
Play Store asset pipeline: crop / resize / validate / save.

Google Play requirements implemented here:
  App icon         512x512, 32-bit PNG (alpha ok), <= 1 MB
  Feature graphic  1024x500, PNG or JPEG, no alpha, <= 15 MB
  Phone screenshot 16:9 or 9:16, each side 320-3840 px, long side <= 2x short side
"""
from __future__ import annotations

import io
import re
import shutil
from pathlib import Path
from typing import Any, Union

from PIL import Image

ICON_SIZE = (512, 512)
FEATURE_SIZE = (1024, 500)
SCREENSHOT_SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
ICON_MAX_BYTES = 1024 * 1024
FEATURE_MAX_BYTES = 15 * 1024 * 1024

ImageLike = Union[str, Path, bytes, Image.Image]


def load_image(src: ImageLike) -> Image.Image:
    if isinstance(src, Image.Image):
        return src.copy()
    if isinstance(src, (bytes, bytearray)):
        img = Image.open(io.BytesIO(src))
    else:
        img = Image.open(str(src))
    img.load()
    return img


def fit_cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale to fully cover `size`, then center-crop (no distortion)."""
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    nw, nh = max(tw, round(img.width * scale)), max(th, round(img.height * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _flatten_rgb(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Remove alpha by compositing on a solid background."""
    if img.mode in ("RGBA", "LA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, bg)
        base.paste(rgba, mask=rgba.split()[3])
        return base
    return img.convert("RGB")


class PlaystoreAssets:
    def __init__(self, project_dir: str):
        self.project_dir = str(Path(project_dir).expanduser().resolve())
        self.assets_dir = str(Path(self.project_dir) / "playstore_assets")

    def ensure_directories(self):
        Path(self.assets_dir).mkdir(parents=True, exist_ok=True)

    # ---- prompts --------------------------------------------------------
    def generate_icon_prompt(self, game_name: str, desc: str = "", genre: str = "",
                             color: str = "", style: str = "flat design") -> str:
        parts = [f'App icon for Android game "{game_name}"', desc, genre,
                 f"{color} color palette" if color else "", style,
                 "high contrast", "Play Store style", "centered subject", "no text"]
        return ", ".join(p.strip() for p in parts if p and p.strip())

    def generate_feature_prompt(self, game_name: str, desc: str = "", genre: str = "",
                                color: str = "", style: str = "flat design") -> str:
        parts = [f'Wide landscape promotional banner for Android game "{game_name}"', desc, genre,
                 f"{color} color palette" if color else "", style,
                 "important elements near the center", "no text"]
        return ", ".join(p.strip() for p in parts if p and p.strip())

    def generate_screenshot_prompt(self, game_name: str, desc: str = "", genre: str = "",
                                   color: str = "", style: str = "flat design",
                                   ratio: str = "9:16") -> str:
        orient = "portrait phone" if ratio == "9:16" else "landscape phone"
        parts = [f'{orient} gameplay screenshot of the Android game "{game_name}"', desc, genre,
                 f"{color} color palette" if color else "", style, "game UI visible", "no text"]
        return ", ".join(p.strip() for p in parts if p and p.strip())

    # ---- savers ---------------------------------------------------------
    def save_app_icon(self, image: ImageLike, filename: str = "icon_512.png") -> str:
        self.ensure_directories()
        img = fit_cover(load_image(image).convert("RGBA"), ICON_SIZE)
        out = Path(self.assets_dir) / filename
        img.save(out, format="PNG", optimize=True)
        if out.stat().st_size > ICON_MAX_BYTES:
            out.unlink()
            raise ValueError("Icon lebih dari 1 MB; coba gambar yang lebih sederhana.")
        return str(out)

    def save_feature_graphic(self, image: ImageLike, filename: str = "feature_graphic_1024x500.png") -> str:
        self.ensure_directories()
        img = fit_cover(_flatten_rgb(load_image(image)), FEATURE_SIZE)
        out = Path(self.assets_dir) / filename
        img.save(out, format="PNG", optimize=True)
        if out.stat().st_size > FEATURE_MAX_BYTES:
            out.unlink()
            img.save(out := out.with_suffix(".jpg"), format="JPEG", quality=90)
        return str(out)

    def save_phone_screenshot(self, image: ImageLike, ratio: str = "9:16") -> str:
        if ratio not in SCREENSHOT_SIZES:
            raise ValueError("ratio must be '9:16' or '16:9'")
        self.ensure_directories()
        img = fit_cover(_flatten_rgb(load_image(image)), SCREENSHOT_SIZES[ratio])
        n = 1
        while (Path(self.assets_dir) / f"phone_screenshot_{n:02d}.png").exists():
            n += 1
        out = Path(self.assets_dir) / f"phone_screenshot_{n:02d}.png"
        img.save(out, format="PNG", optimize=True)
        return str(out)

    # ---- validation / checklist ----------------------------------------
    def validate_assets(self) -> dict[str, Any]:
        """Re-open saved files and check them against Play Store rules."""
        d = Path(self.assets_dir)
        result: dict[str, Any] = {
            "icon": {"ok": False, "detail": "missing", "path": None},
            "feature_graphic": {"ok": False, "detail": "missing", "path": None},
            "screenshots": {"ok": False, "detail": "need at least 2", "paths": []},
        }
        if not d.is_dir():
            return result

        icon = d / "icon_512.png"
        if icon.exists():
            ok, detail = self._check(icon, exact=ICON_SIZE, max_bytes=ICON_MAX_BYTES, fmt={"PNG"})
            result["icon"] = {"ok": ok, "detail": detail, "path": str(icon)}

        feats = sorted(d.glob("feature_graphic_1024x500.*"))
        if feats:
            ok, detail = self._check(feats[0], exact=FEATURE_SIZE, max_bytes=FEATURE_MAX_BYTES,
                                     fmt={"PNG", "JPEG"}, no_alpha=True)
            result["feature_graphic"] = {"ok": ok, "detail": detail, "path": str(feats[0])}

        shots, bad = [], []
        for p in sorted(d.glob("phone_screenshot_*.png")):
            ok, detail = self._check_screenshot(p)
            shots.append(str(p))
            if not ok:
                bad.append(f"{p.name}: {detail}")
        enough = len(shots) >= 2     # Play requires at least 2 phone screenshots
        result["screenshots"] = {
            "ok": enough and not bad,
            "detail": "; ".join(bad) if bad else (f"{len(shots)} file(s)" if enough
                                                  else f"{len(shots)} file(s), need at least 2"),
            "paths": shots,
        }
        return result

    def checklist(self) -> list[dict[str, str]]:
        v = self.validate_assets()
        rows = [
            ("App Icon", "512x512 PNG", v["icon"]),
            ("Feature Graphic", "1024x500", v["feature_graphic"]),
            ("Phone Screenshots", "16:9 / 9:16, min 2", v["screenshots"]),
        ]
        return [{"asset": a, "requirement": r, "status": "OK" if x["ok"] else "TODO",
                 "detail": x["detail"]} for a, r, x in rows]

    @staticmethod
    def _check(path: Path, exact, max_bytes, fmt, no_alpha=False) -> tuple[bool, str]:
        try:
            with Image.open(path) as im:
                if im.format not in fmt:
                    return False, f"format {im.format}"
                if im.size != exact:
                    return False, f"size {im.size[0]}x{im.size[1]}, need {exact[0]}x{exact[1]}"
                if no_alpha and im.mode in ("RGBA", "LA"):
                    return False, "has alpha channel"
        except Exception as exc:  # noqa: BLE001
            return False, f"unreadable: {exc}"
        if path.stat().st_size > max_bytes:
            return False, "file too large"
        return True, f"{exact[0]}x{exact[1]}"

    @staticmethod
    def _check_screenshot(path: Path) -> tuple[bool, str]:
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception as exc:  # noqa: BLE001
            return False, f"unreadable: {exc}"
        short, long_ = min(w, h), max(w, h)
        if short < 320 or long_ > 3840:
            return False, f"{w}x{h} outside 320-3840"
        if long_ > 2 * short:
            return False, f"{w}x{h} ratio over 2:1"
        return True, f"{w}x{h}"

    # ---- buildozer icon -------------------------------------------------
    def apply_icon_to_buildozer_spec(self, icon_path: str | None = None) -> bool:
        """Point buildozer.spec's icon.filename at the saved icon (backup first).
        Returns False when there is no buildozer.spec or no icon yet."""
        spec = Path(self.project_dir) / "buildozer.spec"
        icon = Path(icon_path) if icon_path else Path(self.assets_dir) / "icon_512.png"
        if not spec.is_file() or not icon.is_file():
            return False
        rel = icon.resolve().relative_to(Path(self.project_dir)).as_posix()
        text = spec.read_text(encoding="utf-8")

        backup = Path(self.project_dir) / ".juprisx" / "backup" / "buildozer.spec"
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(spec, backup)

        line = f"icon.filename = %(source.dir)s/{rel}"
        pattern = re.compile(r"^\s*#?\s*icon\.filename\s*=.*$", re.M)
        if pattern.search(text):
            text = pattern.sub(line, text, count=1)
        elif re.search(r"^\[app\]\s*$", text, re.M):
            text = re.sub(r"^\[app\]\s*$", "[app]\n" + line, text, count=1, flags=re.M)
        else:
            text += f"\n[app]\n{line}\n"
        spec.write_text(text, encoding="utf-8")
        return True
