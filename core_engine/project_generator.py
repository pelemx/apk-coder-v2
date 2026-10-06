from __future__ import annotations

import json
import shutil
from pathlib import Path


class WebProjectGenerator:
    """Create the canonical web/ project layout used by the Android container."""

    def __init__(self, project_path: str):
        self.root = Path(project_path).expanduser().resolve()
        self.web = self.root / "web"

    def create(self, name: str | None = None, package_name: str | None = None) -> dict:
        self.web.mkdir(parents=True, exist_ok=True)
        for folder in ("assets/images", "assets/audio", "assets/fonts", "assets/icons"):
            (self.web / folder).mkdir(parents=True, exist_ok=True)
        template = Path(__file__).resolve().parent.parent / "web_templates" / "starter"
        for filename in ("index.html", "app.js", "style.css"):
            src = template / filename
            dst = self.web / filename
            if not dst.exists():
                shutil.copy2(src, dst)
        title = name or self.root.name.replace("_", " ").title()
        manifest = {
            "name": title,
            "short_name": title[:12],
            "start_url": "index.html",
            "display": "fullscreen",
            "orientation": "portrait",
            "offline": True,
            "package": package_name or f"com.juprisx.{self._slug(title)}",
            "engine": "vanilla-canvas",
        }
        (self.web / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "app"
