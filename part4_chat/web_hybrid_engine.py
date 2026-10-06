"""Web-first chat engine adapter.

Keeps the existing MCP/R9 transport and tool callbacks, but changes the generated
application contract from Pygame/Python to HTML5/CSS/JavaScript.
"""
from __future__ import annotations

import re
from typing import Any

from .hybrid_engine import HybridEngine, Reply
from .templates import build_template


WEB_SYSTEM_CONTRACT = """
JUPRISX WEB-TO-ANDROID BUILDER CONTRACT

The generated application is an offline-first HTML5/CSS/JavaScript application.
It is packaged into a native Android WebView and built with Gradle.

STRICT RULES:
- NEVER generate Python, Pygame, pygame-ce, SDL2, Buildozer, or python-for-android code.
- The project entry point MUST be web/index.html (or index.html when project root is web).
- Generate HTML5 + CSS + modern JavaScript only.
- Canvas or Phaser may be used; Phaser must be bundled locally, never loaded from a CDN.
- Mobile-first viewport is mandatory.
- Prefer Pointer Events for touch/mouse/stylus compatibility.
- Prevent accidental page scrolling/selection in game surfaces.
- All images, audio, fonts, JSON and libraries must use relative local paths.
- NEVER use http:// or https:// CDN resources inside generated application files.
- The app must work with Android WebView while offline.
- Handle Android back navigation through browser history/app state where applicable.
- Keep generated code self-contained and production-oriented.

OUTPUT FORMAT:
Return complete changed/new files as fenced blocks. The first line inside every
block MUST be `// file: relative/path` for JS/CSS/JSON or `<!-- file: relative/path -->`
for HTML. Use paths relative to the generated project.
""".strip()


class WebHybridEngine(HybridEngine):
    """HybridEngine with an immutable HTML/JS/CSS generation contract."""

    @staticmethod
    def extract_game_name(prompt: str) -> str:
        m = re.search(
            r"(?:bikin|buat|generate|create|make)\s+(?:sebuah\s+)?(?:game\s+)?(.+)",
            prompt,
            re.I,
        )
        name = (m.group(1) if m else prompt).strip(" .!?")
        name = re.sub(r"^(game|html|web)\s+", "", name, flags=re.I)
        return name[:60] or "HTML5 App"

    def _do_generate(self, prompt: str) -> Reply:
        name = self.extract_game_name(prompt)
        files: dict[str, str] = {}
        source = "template lokal"
        request = f"""{WEB_SYSTEM_CONTRACT}

USER REQUEST:
{prompt}

Generate a complete runnable project. Include index.html, app.js, style.css and
any local assets/manifests required by the request. Do not emit Python files.
"""
        text = self._call_mcp(
            request,
            "generate_web_app",
            timeout=self.cfg["mcp_timeout_generate"],
            include_sources=True,
        )
        if text:
            files = self.parse_files(text)
            if files and not any(p.lower().endswith(".py") for p in files):
                source = "MCP / JuprisX"
            else:
                files = {}
        if not files:
            files = build_template(name)

        return Reply(
            f"Web app **{name}** siap ({source}). File: {', '.join(sorted(files))}.\n"
            "Pilih folder untuk menyimpan project, atau ketik *simpan di default*.",
            action="create_project",
            data={"name": name.title(), "slug": self._web_slug(name), "files": files, "source": source},
        )

    def _do_fix(self, prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        project = self.ctx.project or {}
        findings = project.get("findings", [])
        request = f"""{WEB_SYSTEM_CONTRACT}

Fix the active HTML/JS/CSS project according to the user's request.
Do not rewrite unrelated files. Do not generate Python.

USER REQUEST:
{prompt}

FINDINGS:
{findings}
"""
        text = self._call_mcp(
            request,
            "request_web_patch",
            timeout=self.cfg["mcp_timeout_generate"],
            include_sources=True,
        )
        files = self.parse_files(text) if text else {}
        files = {k: v for k, v in files.items() if not k.lower().endswith(".py")}
        if files:
            edits = [{"file": k, "content": v} for k, v in files.items()]
            return Reply(
                f"Dapat {len(edits)} web patch dari AI. Cek diff di Reviewer lalu Approve/Reject.",
                action="stage_edits",
                data={"edits": edits},
            )
        return Reply("MCP tidak mengembalikan patch HTML/JS/CSS. Tidak ada file yang diubah.")

    def _do_setup_env(self, _prompt: str) -> Reply:
        return Reply(
            "Web build environment: cek Python tooling, JDK, Android SDK dan Gradle. "
            "Buildozer/p4a/pygame tidak diperlukan untuk application packaging.",
            action="setup_env",
        )

    def _do_check_env(self, _prompt: str) -> Reply:
        return Reply(
            "Web Android build uses native Gradle/WebView. Required: JDK, Android SDK, "
            "Gradle wrapper and WebView template. Buildozer/p4a/pygame are not required."
        )

    def _do_chat(self, prompt: str) -> Reply:
        return super()._do_chat(prompt + "\n\n" + WEB_SYSTEM_CONTRACT)

    @staticmethod
    def _web_slug(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug or "html5-app"
