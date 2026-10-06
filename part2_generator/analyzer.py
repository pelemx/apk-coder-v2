from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any


from .common import (
    EXCLUDES as DEFAULT_EXCLUDES, import_aliases, is_excluded, iter_string_constants,
    looks_like_unix_absolute_path, looks_like_windows_absolute_path, resolve_call_name,
)

WINDOWS_ONLY_MODULES = {"winsound", "msvcrt", "_winreg", "winreg", "pythoncom", "pywintypes", "wmi", "comtypes"}

# Signals that a game adapts to the device screen instead of fixing a desktop window size.
DISPLAY_ADAPTIVE_CALLS = {
    "pygame.display.Info", "pygame.display.get_desktop_sizes", "pygame.display.get_window_size",
}

SOURCE_EXTENSIONS = {".py"}
CONFIG_FILES = {
    "requirements.txt", "pyproject.toml", "setup.py",
    "setup.cfg", "buildozer.spec",
}


class Analyzer:
    """Static analyzer for Pygame projects against the immutable Builder contract."""

    def __init__(self, project_path: str, builder_contract: dict[str, Any] | None = None):
        self.project_path = Path(project_path).expanduser().resolve()
        self.builder_contract = builder_contract or self.default_builder_contract()

    @staticmethod
    def default_builder_contract() -> dict[str, Any]:
        return {
            "name": "JuprisX Pygame Builder",
            "version": "1.0",
            "runtime": {"os": "WSL", "python": "fixed", "pygame": "fixed"},
            "filesystem": {
                "working_directory": "project_root",
                "windows_absolute_paths": False,
                "case_sensitive": True,
            },
            "pygame": {
                "display": "builder_managed",
                "resolution": "builder_managed",
                "font_system": "bundled_fonts",
                "audio": "builder_managed",
            },
            "rules": [
                "Do not modify builder",
                "Do not require Windows-only APIs",
                "Do not assume host-installed fonts",
                "Do not use hardcoded absolute paths",
                "Use project-relative assets",
            ],
        }

    def analyze(self) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        files_scanned = 0

        if not self.project_path.exists():
            return {
                "status": "error",
                "findings": [{
                    "severity": "HIGH",
                    "code": "PROJECT_NOT_FOUND",
                    "file": str(self.project_path),
                    "line": 0,
                    "message": "Project directory does not exist.",
                }],
                "files_scanned": 0,
            }

        for path in self._iter_project_files():
            files_scanned += 1
            if path.suffix == ".py":
                findings.extend(self._analyze_python_file(path))
            elif path.name == "requirements.txt":
                findings.extend(self._analyze_requirements(path))
            elif path.name == "buildozer.spec":
                findings.extend(self._analyze_buildozer(path))

        return {
            "status": "analyzed",
            "files_scanned": files_scanned,
            "findings": findings,
        }

    def _iter_project_files(self):
        for path in self.project_path.rglob("*"):
            if not path.is_file():
                continue
            if is_excluded(path.relative_to(self.project_path).parts):
                continue
            if path.suffix in SOURCE_EXTENSIONS or path.name in CONFIG_FILES:
                yield path

    def _analyze_python_file(self, path: Path) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(self._finding("MED", "NON_UTF8_SOURCE", path, 0,
                                          "Python source is not UTF-8; scanner skipped AST analysis."))
            return findings

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append(self._finding(
                "HIGH", "PYTHON_SYNTAX_ERROR", path, exc.lineno or 0,
                f"Python syntax error: {exc.msg}",
            ))
            return findings

        aliases = import_aliases(tree)
        display_calls: list[ast.Call] = []
        adaptive = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = resolve_call_name(node.func, aliases)
                if name == "pygame.font.SysFont":
                    findings.append(self._finding(
                        "HIGH", "HOST_DEPENDENT_FONT", path, node.lineno,
                        "pygame.font.SysFont() can depend on host-installed fonts. "
                        "Builder contract requires bundled fonts.",
                        "Use pygame.font.Font() with a project-relative bundled font.",
                    ))
                elif name == "pygame.display.set_mode":
                    display_calls.append(node)
                elif name in DISPLAY_ADAPTIVE_CALLS:
                    adaptive = True

        # Display is builder-managed: only a project that hardcodes a window size and does
        # nothing to adapt to the device screen is a finding.
        if self.builder_contract.get("pygame", {}).get("display") == "builder_managed":
            for call in display_calls:
                if not adaptive and self._hardcodes_display(call, aliases):
                    findings.append(self._finding(
                        "MED", "BUILDER_MANAGED_DISPLAY", path, call.lineno,
                        "set_mode() uses a fixed window size and the file does not adapt to the "
                        "device resolution.",
                        "Use size (0, 0) to let Android handle scaling natively, or derive the size from "
                        "pygame.display.Info(). CRITICAL: NEVER use pygame.SCALED.", # <--- SUDAH AMAN
                    ))

        for node, value in iter_string_constants(tree):
            line = getattr(node, "lineno", 0)
            if looks_like_windows_absolute_path(value):
                findings.append(self._finding(
                    "HIGH", "WINDOWS_ABSOLUTE_PATH", path, line,
                    f"Hardcoded Windows absolute path found: {value}",
                    "Use pathlib and a project-relative path.",
                ))
            elif looks_like_unix_absolute_path(value):
                findings.append(self._finding(
                    "MED", "ABSOLUTE_PATH", path, line,
                    f"Hardcoded absolute path found: {value}",
                    "Use a project-relative path derived from the project root.",
                ))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if self._is_windows_only_module(alias.name):
                        findings.append(self._finding(
                            "HIGH", "WINDOWS_ONLY_IMPORT", path, node.lineno,
                            f"Windows-only dependency imported: {alias.name}",
                            "Replace it with a cross-platform/WSL-compatible implementation.",
                        ))
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                if self._is_windows_only_module(node.module or ""):
                    findings.append(self._finding(
                        "HIGH", "WINDOWS_ONLY_IMPORT", path, node.lineno,
                        f"Windows-only dependency imported: {node.module}",
                        "Replace it with a cross-platform/WSL-compatible implementation.",
                    ))

        return findings

    @staticmethod
    def _is_windows_only_module(name: str) -> bool:
        root = name.split(".")[0]
        return root in WINDOWS_ONLY_MODULES or root.startswith("win32")

    @staticmethod
    def _hardcodes_display(call: ast.Call, aliases: dict[str, str]) -> bool:
        size = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "size"), None)
        flags = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "flags"), None)
        
        # FIX: Wajibkan FULLSCREEN, tolak SCALED
        if flags is not None:
            for sub in ast.walk(flags):
                if isinstance(sub, (ast.Attribute, ast.Name)):
                    leaf = sub.attr if isinstance(sub, ast.Attribute) else sub.id
                    # Jika pakai FULLSCREEN dan ukurannya (0, 0), berarti lolos (False)
                    if leaf == "FULLSCREEN" and _is_zero_size(size):
                        return False
                        
        if _is_zero_size(size):
            return False
        if size is None:
            return False
            
        if isinstance(size, (ast.Tuple, ast.List)):
            return True
        return isinstance(size, ast.Name) and size.id.isupper()

    def _analyze_requirements(self, path: Path) -> list[dict[str, Any]]:
        findings = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return [self._finding("MED", "NON_UTF8_REQUIREMENTS", path, 0,
                                   "requirements.txt is not UTF-8.")]
        for idx, raw in enumerate(lines, 1):
            line = raw.strip().lower()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("pywin32", "pywin32-")):
                findings.append(self._finding(
                    "HIGH", "WINDOWS_ONLY_DEPENDENCY", path, idx,
                    f"Windows-only dependency detected: {raw.strip()}",
                    "Remove or replace it with a WSL/Linux-compatible dependency.",
                ))
        return findings

    def _analyze_buildozer(self, path: Path) -> list[dict[str, Any]]:
        findings = []
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return [self._finding("MED", "NON_UTF8_BUILDOZER", path, 0,
                                   "buildozer.spec is not UTF-8.")]
        if "source.include_exts" not in text:
            findings.append(self._finding(
                "LOW", "BUILDOZER_EXTENSIONS_UNDECLARED", path, 0,
                "buildozer.spec does not declare source.include_exts.",
                "Declare the file extensions/assets required by the project.",
            ))
        return findings




    @staticmethod
    def _finding(severity, code, path, line, message, recommendation=None):
        item = {
            "severity": severity,
            "code": code,
            "file": str(path),
            "line": line,
            "message": message,
        }
        if recommendation:
            item["recommended_action"] = recommendation
        return item


def _is_zero_size(node) -> bool:
    return (isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) == 2
            and all(isinstance(e, ast.Constant) and e.value == 0 for e in node.elts))
