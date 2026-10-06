from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EXCLUDED = {".git", ".juprisx", "node_modules", "dist", "build", "__pycache__", "venv", ".venv"}
TEXT_EXTENSIONS = {".html", ".js", ".css", ".json"}


class Analyzer:
    """Static analyzer for the immutable JuprisX HTML/JS Android WebView contract."""

    def __init__(self, project_path: str, builder_contract: dict[str, Any] | None = None):
        self.project_path = Path(project_path).expanduser().resolve()
        self.builder_contract = builder_contract or self.default_builder_contract()

    @staticmethod
    def default_builder_contract() -> dict[str, Any]:
        return {
            "name": "JuprisX HTML/JS Android Builder",
            "version": "2.0",
            "runtime": {"android": True, "webview": True, "offline_first": True},
            "entry": "web/index.html",
            "rules": [
                "No Python/Pygame runtime in generated app",
                "No CDN or remote runtime dependencies",
                "No absolute desktop paths",
                "Use relative local assets",
                "Use mobile viewport and touch/pointer input",
            ],
        }

    def analyze(self) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        if not self.project_path.exists():
            return {"status": "error", "files_scanned": 0, "findings": [self._finding("HIGH", "PROJECT_NOT_FOUND", self.project_path, 0, "Project directory does not exist.")]}
        web = self.project_path / "web"
        if not web.exists():
            web = self.project_path
        index = web / "index.html"
        if not index.exists():
            findings.append(self._finding("HIGH", "MISSING_ENTRY", index, 0, "Required web/index.html entry point is missing.", "Create web/index.html."))
        files_scanned = 0
        for path in web.rglob("*"):
            if not path.is_file() or any(part in EXCLUDED for part in path.relative_to(web).parts):
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            files_scanned += 1
            if path.suffix.lower() == ".html":
                findings.extend(self._analyze_html(path, web))
            elif path.suffix.lower() == ".js":
                findings.extend(self._analyze_js(path, web))
            elif path.suffix.lower() == ".css":
                findings.extend(self._analyze_css(path, web))
            elif path.name == "manifest.json":
                findings.extend(self._analyze_manifest(path))
        return {"status": "analyzed", "files_scanned": files_scanned, "findings": findings}

    def _analyze_html(self, path: Path, web: Path) -> list[dict[str, Any]]:
        source = path.read_text(encoding="utf-8", errors="replace")
        findings: list[dict[str, Any]] = []
        if path.name == "index.html":
            low = source.lower()
            if "meta" not in low or not re.search(r'<meta[^>]+name=["\']viewport["\']', source, re.I):
                findings.append(self._finding("HIGH", "MISSING_VIEWPORT", path, 1, "Mobile viewport meta tag is missing.", "Add a responsive viewport meta tag."))
        for line_no, line in enumerate(source.splitlines(), 1):
            for match in re.finditer(r'(?:src|href)=["\']([^"\']+)', line, re.I):
                findings.extend(self._check_reference(path, web, match.group(1), line_no))
            if re.search(r'<script[^>]+src=["\']https?://', line, re.I):
                findings.append(self._finding("HIGH", "REMOTE_SCRIPT", path, line_no, "External script/CDN dependency detected.", "Bundle the script locally."))
        return findings

    def _analyze_js(self, path: Path, web: Path) -> list[dict[str, Any]]:
        source = path.read_text(encoding="utf-8", errors="replace")
        findings: list[dict[str, Any]] = []
        if re.search(r'(?<![A-Za-z])(?:file://|https?://)', source, re.I):
            findings.append(self._finding("HIGH", "REMOTE_OR_FILE_URL", path, 1, "Runtime URL dependency detected.", "Use local relative assets."))
        for line_no, line in enumerate(source.splitlines(), 1):
            for match in re.finditer(r'(?:fetch|import|from)\s*\(?["\']([^"\']+)', line, re.I):
                findings.extend(self._check_reference(path, web, match.group(1), line_no))
        return findings

    def _analyze_css(self, path: Path, web: Path) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        source = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(source.splitlines(), 1):
            for match in re.finditer(r'url\(\s*["\']?([^\)"\']+)', line, re.I):
                findings.extend(self._check_reference(path, web, match.group(1).strip(), line_no))
        return findings

    def _check_reference(self, path: Path, web: Path, ref: str, line: int) -> list[dict[str, Any]]:
        parsed = urlparse(ref)
        if parsed.scheme in {"http", "https"}:
            return [self._finding("HIGH", "REMOTE_DEPENDENCY", path, line, f"Remote dependency: {ref}", "Bundle the dependency locally.")]
        if parsed.scheme == "file" or ref.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", ref):
            return [self._finding("HIGH", "ABSOLUTE_ASSET_PATH", path, line, f"Absolute/desktop path: {ref}", "Use a project-relative path.")]
        if ref.startswith(("#", "data:", "blob:", "javascript:")):
            return []
        clean = ref.split("?", 1)[0].split("#", 1)[0]
        target = (path.parent / clean).resolve()
        if not target.is_file():
            return [self._finding("HIGH", "BROKEN_ASSET", path, line, f"Local resource not found: {ref}", "Generate or add the missing asset.")]
        return []

    @staticmethod
    def _analyze_manifest(path: Path) -> list[dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return [Analyzer._finding("HIGH", "MANIFEST_JSON", path, exc.lineno or 0, "manifest.json is invalid JSON.")]
        findings = []
        for key in ("name", "short_name", "start_url"):
            if not data.get(key):
                findings.append(Analyzer._finding("MED", "MANIFEST_FIELD", path, 1, f"Missing manifest field: {key}"))
        return findings

    @staticmethod
    def _finding(severity, code, path, line, message, recommendation=None):
        item = {"severity": severity, "code": code, "file": str(path), "line": line, "message": message}
        if recommendation:
            item["recommended_action"] = recommendation
        return item
