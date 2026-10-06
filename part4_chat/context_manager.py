"""
Context manager for the chat tab.

Holds the chat mode, the active project and working directory, and builds the
compact project summary that is sent to the AI (MCP) as context.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

MODES = ("General Chat", "Project Context", "New Project")
EXCLUDES = {".git", "__pycache__", ".venv", "venv", "node_modules",
            "build", "dist", "cache", ".juprisx", ".buildozer", "bin"}


class ContextManager:
    def __init__(self):
        self.mode: str = "General Chat"
        self.project: dict[str, Any] | None = None
        self.active_working_dir: str | None = None

    # ---- mode -----------------------------------------------------------
    def set_mode(self, mode: str) -> bool:
        if mode not in MODES:
            return False
        self.mode = mode
        return True

    # ---- project / working dir -----------------------------------------
    def set_project(self, project: dict | None):
        self.project = project
        self.active_working_dir = project.get("working_dir") if project else None

    def set_working_dir(self, working_dir: str):
        path = Path(working_dir).expanduser()
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {working_dir}")
        self.active_working_dir = str(path.resolve())
        if self.project and self.project.get("working_dir") != self.active_working_dir:
            self.project = None  # project no longer matches the chosen folder

    def get_working_dir(self) -> str | None:
        return self.active_working_dir

    def clear_context(self):
        self.project = None
        self.active_working_dir = None

    @property
    def has_project(self) -> bool:
        return self.project is not None and bool(self.active_working_dir)

    # ---- context for the AI --------------------------------------------
    def list_python_files(self) -> list[Path]:
        if not self.active_working_dir:
            return []
        root = Path(self.active_working_dir)
        out = []
        for p in sorted(root.rglob("*.py")):
            if any(part in EXCLUDES for part in p.relative_to(root).parts):
                continue
            out.append(p)
        return out

    def collect_sources(self, max_chars: int = 24000) -> dict[str, str]:
        """Project .py sources (relative path -> text), capped so prompts stay small."""
        root = Path(self.active_working_dir) if self.active_working_dir else None
        sources: dict[str, str] = {}
        used = 0
        for p in self.list_python_files():
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if used + len(text) > max_chars:
                break
            sources[p.relative_to(root).as_posix()] = text
            used += len(text)
        return sources

    def build_context(self, include_sources: bool = False) -> dict[str, Any]:
        ctx: dict[str, Any] = {
            "mode": self.mode,
            "working_dir": self.active_working_dir,
            # ATURAN PAKSAAN UNTUK ANDROID PYGAME
            "builder_rules": [
                "CRITICAL: NEVER use pygame.SCALED. Use pygame.display.set_mode((WIDTH, HEIGHT)) only.",
                "CRITICAL: NEVER use 'if __name__ == \"__main__\":'. Call main() directly at the end of the file.",
                "No Windows-only APIs", 
                "No host-installed fonts (no SysFont, use pygame.font.Font(None, size))",
                "No hardcoded absolute paths", 
                "Use project-relative assets",
                "Handle android back button: if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: running = False",
                "Do not modify the builder",
            ],
        }
        if self.project and self.mode != "General Chat":
            ctx["project"] = {
                "name": self.project.get("name"),
                "status": self.project.get("status"),
                "findings": [
                    {k: f.get(k) for k in ("severity", "code", "file", "line", "message")}
                    for f in self.project.get("findings", [])[:20]
                ],
            }
        if include_sources and self.active_working_dir:
            ctx["files"] = self.collect_sources()
        return ctx

    def status_line(self) -> str:
        proj = self.project.get("name") if self.project else "-"
        return f"Mode: {self.mode} | Project: {proj} | Dir: {self.active_working_dir or '(none)'}"
