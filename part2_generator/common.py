"""Shared constants/helpers for the analyzer and the validator (single source of truth)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

# Folders that are never project source: VCS, caches, virtualenvs and build output.
EXCLUDES = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    "build", "dist", "cache", "bin", ".buildozer", ".gradle", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".juprisx",
}


def is_excluded(relative_parts: tuple[str, ...]) -> bool:
    return any(part in EXCLUDES or part.endswith(".egg-info") for part in relative_parts)


def iter_python_files(project_path: Path) -> Iterator[Path]:
    if not project_path.exists():
        return
    for path in project_path.rglob("*.py"):
        if path.is_file() and not is_excluded(path.relative_to(project_path).parts):
            yield path


# ---------------------------------------------------------------- shared string/path helpers
import ast
import re

_UNIX_ROOTS = {
    "home", "usr", "mnt", "etc", "var", "tmp", "opt", "root", "srv", "bin", "lib",
    "sdcard", "storage", "data", "media", "Users", "Applications",
}
_WIN_ABS = re.compile(r"^[A-Za-z]:[\\/]")
_UNC = re.compile(r"^\\\\[^\\/\s]")


def looks_like_windows_absolute_path(value: str) -> bool:
    return bool(_WIN_ABS.match(value)) or bool(_UNC.match(value))


def looks_like_unix_absolute_path(value: str) -> bool:
    """'/home/me/x', '/sdcard/a.png' yes; '/ 2', '/', '//cdn', '/n' no."""
    if not value.startswith("/") or value.startswith("//") or any(c.isspace() for c in value):
        return False
    first = value[1:].split("/", 1)[0]
    return first in _UNIX_ROOTS


def docstring_node_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def iter_string_constants(tree: ast.AST):
    """Yield (node, value) for string literals that are real data, not docstrings."""
    skip = docstring_node_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node, node.value


def import_aliases(tree: ast.AST) -> dict[str, str]:
    """Map local names to canonical dotted names, e.g. {'pg': 'pygame', 'font': 'pygame.font',
    'SysFont': 'pygame.font.SysFont'}."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    aliases[top] = top
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for a in node.names:
                if a.name == "*":
                    if node.module == "pygame":
                        aliases.setdefault("font", "pygame.font")
                        aliases.setdefault("display", "pygame.display")
                    continue
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"
    return aliases


def resolve_call_name(func: ast.AST, aliases: dict[str, str]) -> str:
    """Dotted canonical name of a call target, resolving import aliases ('' if unknown)."""
    parts: list[str] = []
    cur = func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return ""
    root = aliases.get(cur.id, cur.id)
    return ".".join([root] + list(reversed(parts)))
