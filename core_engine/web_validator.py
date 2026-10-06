from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


class WebValidator:
    """Validate an offline-first HTML/JS/CSS project before Android packaging."""

    ASSET_RE = re.compile(r"(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.I)
    IMPORT_RE = re.compile(r"(?:import\s+[^;]*?from\s*|import\s*)[\"']([^\"']+)[\"']", re.I)
    URL_RE = re.compile(r"url\(\s*[\"']?([^\)\"']+)", re.I)

    def __init__(self, project_path: str):
        self.root = Path(project_path).expanduser().resolve()

    def validate(self) -> dict:
        findings: list[dict] = []
        web = self.root / "web"
        if not web.exists():
            web = self.root

        index = web / "index.html"
        if not index.exists():
            findings.append(self._f("HIGH", "MISSING_ENTRY", "index.html", 0, "Web entry point index.html is missing."))
            return self._result(findings, 0)

        html = index.read_text(encoding="utf-8", errors="replace")
        low = html.lower()
        if 'name="viewport"' not in low and "name='viewport'" not in low:
            findings.append(self._f("HIGH", "MISSING_VIEWPORT", "index.html", 0, "Mobile viewport meta tag is missing."))
        if re.search(r"<script[^>]+src=[\"']https?://", html, re.I):
            findings.append(self._f("HIGH", "REMOTE_SCRIPT", "index.html", 0, "External script/CDN dependency detected."))
        if re.search(r"(?:src|href)=[\"']http://", html, re.I):
            findings.append(self._f("HIGH", "INSECURE_RESOURCE", "index.html", 0, "HTTP resource detected; offline build must use local assets."))

        files = list(web.rglob("*")) if web.exists() else []
        file_set = {p.resolve() for p in files if p.is_file()}
        text_files = [p for p in files if p.is_file() and p.suffix.lower() in {".html", ".js", ".css"}]
        scanned = 0
        for path in text_files:
            scanned += 1
            source = path.read_text(encoding="utf-8", errors="replace")
            refs = self.ASSET_RE.findall(source) + self.IMPORT_RE.findall(source) + self.URL_RE.findall(source)
            for ref in refs:
                ref = ref.strip()
                if not ref or ref.startswith(("#", "data:", "blob:", "javascript:")):
                    continue
                parsed = urlparse(ref)
                if parsed.scheme in {"http", "https"}:
                    findings.append(self._f("HIGH", "REMOTE_DEPENDENCY", str(path.relative_to(web)), 0, f"Remote dependency: {ref}"))
                    continue
                if parsed.scheme or ref.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", ref):
                    findings.append(self._f("HIGH", "ABSOLUTE_ASSET_PATH", str(path.relative_to(web)), 0, f"Desktop/absolute asset path: {ref}"))
                    continue
                clean = ref.split("?", 1)[0].split("#", 1)[0]
                target = (path.parent / clean).resolve()
                if target not in file_set and not target.is_file():
                    findings.append(self._f("HIGH", "BROKEN_ASSET", str(path.relative_to(web)), 0, f"Referenced local asset does not exist: {ref}"))

        manifest = web / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                for key in ("name", "short_name", "start_url"):
                    if not data.get(key):
                        findings.append(self._f("MED", "MANIFEST_FIELD", "manifest.json", 0, f"Missing manifest field: {key}"))
            except json.JSONDecodeError as exc:
                findings.append(self._f("HIGH", "MANIFEST_JSON", "manifest.json", exc.lineno or 0, "manifest.json is invalid JSON."))

        return self._result(findings, scanned)

    @staticmethod
    def _f(severity, code, file, line, message):
        return {"severity": severity, "code": code, "file": file, "line": line, "message": message}

    @staticmethod
    def _result(findings, scanned):
        return {"status": "passed" if not any(f["severity"] == "HIGH" for f in findings) else "failed", "passed": not findings, "files_scanned": scanned, "findings": findings}
