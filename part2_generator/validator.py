from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from .common import (
    EXCLUDES, iter_python_files, iter_string_constants,
    looks_like_windows_absolute_path,
)

# Provided by the Builder / Android runtime, never installed on the Windows host.
BUILDER_PROVIDED = {"pygame", "android", "jnius", "kivy"}

# requirement name -> import name, where they differ.
IMPORT_NAMES = {
    "pillow": "PIL", "opencv-python": "cv2", "opencv-python-headless": "cv2", "pyyaml": "yaml",
    "beautifulsoup4": "bs4", "scikit-learn": "sklearn", "pygame-ce": "pygame",
}
WINDOWS_ONLY_PACKAGES = {"pywin32", "pypiwin32", "pywinauto", "comtypes", "wmi", "winshell", "pywin32-ctypes"}


class Validator:
    """Deterministic checks. Nothing is reported as passed by default and no project code is run."""

    def __init__(self, project_path: str, expected_python: str | None = None,
                 env_status: dict[str, Any] | None = None):
        self.project_path = Path(project_path).expanduser().resolve()
        self.expected_python = expected_python
        self._env = env_status  # build-environment status; fetched lazily if not injected

    # ------------------------------------------------------------------ build environment
    def _env_status(self) -> dict[str, Any]:
        if self._env is None:
            from part1_builder.wsl_checker import cached_check
            self._env = cached_check()
        return self._env

    def validate_wsl(self) -> bool:
        """Is the BUILD environment (WSL, reached via wsl.exe on Windows) usable?"""
        return bool(self._env_status().get("ready"))

    def validate_pygame(self) -> bool:
        return bool(self._env_status().get("pygame_installed"))

    # ------------------------------------------------------------------ project checks
    def validate_syntax(self) -> bool:
        if not self.project_path.exists():
            return False
        for path in self._python_files():
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError, OSError):
                return False
        return True

    def unresolved_imports(self) -> list[dict[str, Any]]:
        """Static import resolution (nothing is imported or executed).

        Resolution order: project's own modules -> stdlib -> Builder-provided ->
        declared requirements -> installed on this machine (spec lookup only)."""
        local = self._local_module_names()
        declared = self._declared_requirements()
        missing: list[dict[str, Any]] = []
        for path in self._python_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except Exception:  # noqa: BLE001
                missing.append({"file": str(path), "line": 0, "module": "<unparsable>"})
                continue
            optional = self._optional_import_nodes(tree)
            for node in ast.walk(tree):
                if id(node) in optional:
                    continue
                names: list[tuple[str, int]] = []
                if isinstance(node, ast.Import):
                    names = [(a.name.split(".")[0], node.lineno) for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [(node.module.split(".")[0], node.lineno)]
                for top, line in names:
                    if not self._resolves(top, local, declared):
                        missing.append({"file": str(path), "line": line, "module": top})
        return missing

    def validate_imports(self) -> bool:
        return not self.unresolved_imports()

    def validate_builder_constraints(self) -> bool:
        for path in self._python_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                return False
            for _, value in iter_string_constants(tree):
                if looks_like_windows_absolute_path(value):
                    return False
        return True

    def validate_dependencies(self) -> bool:
        """No Windows-only packages declared. Runtime availability is decided by Buildozer's
        recipes in the build environment, so host-installed packages are irrelevant."""
        for name in self._declared_requirements(raw=True):
            if name in WINDOWS_ONLY_PACKAGES:
                return False
        return True

    def validate_all(self) -> dict[str, Any]:
        results = {
            "syntax": self.validate_syntax(),
            "imports": self.validate_imports(),
            "pygame": self.validate_pygame(),
            "wsl": self.validate_wsl(),
            "builder": self.validate_builder_constraints(),
            "dependencies": self.validate_dependencies(),
        }
        results["passed"] = all(results.values())
        return results

    # ------------------------------------------------------------------ helpers
    def _python_files(self):
        yield from iter_python_files(self.project_path)

    def _local_module_names(self) -> set[str]:
        names: set[str] = set()
        for path in self._python_files():
            names.add(path.stem)
            for part in path.relative_to(self.project_path).parts[:-1]:
                names.add(part)
        return names

    def _declared_requirements(self, raw: bool = False) -> set[str]:
        names: set[str] = set()
        req = self.project_path / "requirements.txt"
        if req.exists():
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    names.add(re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip().lower())
        spec = self.project_path / "buildozer.spec"
        if spec.exists():
            for line in spec.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^\s*requirements\s*=\s*(.+)$", line)
                if m:
                    names.update(x.strip().split("==")[0].lower() for x in m.group(1).split(",") if x.strip())
        if raw:
            return names
        out: set[str] = set()
        for n in names:
            out.add(IMPORT_NAMES.get(n, n).replace("-", "_"))
            out.add(n.replace("-", "_"))
        return out

    @staticmethod
    def _optional_import_nodes(tree: ast.AST) -> set[int]:
        """Imports inside `try: ... except ImportError` are optional by design."""
        ids: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                catches = False
                for h in node.handlers:
                    t = h.type
                    labels = [getattr(e, "id", "") for e in (t.elts if isinstance(t, ast.Tuple) else [t])] if t else ["Exception"]
                    if any(l in {"ImportError", "ModuleNotFoundError", "Exception"} for l in labels):
                        catches = True
                if catches:
                    for stmt in node.body:
                        for sub in ast.walk(stmt):
                            ids.add(id(sub))
        return ids

    @staticmethod
    def _resolves(top: str, local: set[str], declared: set[str]) -> bool:
        if top in local or top in BUILDER_PROVIDED or top in declared:
            return True
        if top in getattr(sys, "stdlib_module_names", ()):
            return True
        try:
            return importlib.util.find_spec(top) is not None  # top-level lookup only, no execution
        except (ImportError, ValueError, AttributeError):
            return False
