"""HTML/JS/CSS-first generation engine."""
from __future__ import annotations
import re
from .hybrid_engine import HybridEngine, Reply
from .templates import build_template

WEB_SYSTEM_CONTRACT = """JUPRISX WEB-TO-ANDROID CONTRACT
- Generate HTML5, CSS and modern JavaScript only.
- NEVER generate Python, Pygame, pygame-ce, SDL2, Buildozer or python-for-android app code.
- Entry point is web/index.html.
- Mobile-first viewport and Pointer Events are required.
- All runtime assets and libraries are local and relative; no CDN/http/file URLs.
- Phaser is allowed only when bundled locally under web/assets/.
- Android packaging is handled by the native Gradle WebView container.
- Generated app must work offline.
"""

class WebHybridEngine(HybridEngine):
    def handle(self, prompt):
        action = self._action(prompt)
        handlers = {
            "generate": self._do_generate, "fix": self._do_fix,
            "scan": lambda _: Reply("Scan active project.", "scan"),
            "build": lambda _: Reply("Build APK + AAB.", "build"),
            "keystore": lambda _: Reply("Generate/reuse release keystore.", "keystore"),
            "assets": lambda _: Reply("Open Play Store asset generator.", "assets"),
            "auto_fix": lambda _: Reply("Run bounded web fix loop.", "auto_fix"),
            "check_env": lambda _: Reply("Check Android Gradle environment.", "setup_env"),
            "check_mcp": lambda _: Reply(self.diagnose()),
        }
        if action in handlers: return handlers[action](prompt)
        return super()._do_chat(prompt + "\n\n" + WEB_SYSTEM_CONTRACT)

    @staticmethod
    def _action(prompt):
        p = prompt.lower()
        if re.search(r"\b(bikin|buat|generate|create|make|coding|tulis)\b", p): return "generate"
        if re.search(r"auto.?fix|perbaiki otomatis", p): return "auto_fix"
        if re.search(r"\b(fix|patch|benerin|perbaiki)\b", p): return "fix"
        if re.search(r"\b(scan|analisis|analyze)\b", p): return "scan"
        if re.search(r"\b(apk|aab|build|compile|release)\b", p): return "build"
        if "keystore" in p or "signing key" in p: return "keystore"
        if any(x in p for x in ("icon", "asset", "screenshot", "playstore", "feature graphic")): return "assets"
        if re.search(r"check.*(env|android|gradle|jdk|sdk|wsl)|cek.*(env|android|gradle|jdk|sdk|wsl)", p): return "check_env"
        if re.search(r"check.*mcp|cek.*mcp", p): return "check_mcp"
        return "chat"

    def _do_generate(self, prompt):
        name = self._name(prompt)
        text = self._call_mcp(WEB_SYSTEM_CONTRACT + "\nUSER REQUEST:\n" + prompt + "\nReturn complete runnable project files.", "generate_web_app", self.cfg.get("mcp_timeout_generate", 90), True)
        files = self.parse_files(text); source = "MCP / JuprisX"
        if not files or any(p.lower().endswith(".py") for p in files): files = build_template(name); source = "local template"
        return Reply(f"Web app **{name}** ready. Files: {', '.join(sorted(files))}. Choose a folder or type *simpan di default*.", "create_project", {"name": name.title(), "slug": self._slug(name), "files": files, "source": source})

    def _do_fix(self, prompt):
        if not self.ctx.has_project: return Reply("Attach/select a project first.")
        text = self._call_mcp(WEB_SYSTEM_CONTRACT + "\nFix this active project.\n" + prompt, "request_web_patch", self.cfg.get("mcp_timeout_generate", 90), True)
        files = {k:v for k,v in self.parse_files(text).items() if not k.lower().endswith(".py")}
        if not files: return Reply("AI returned no safe HTML/JS/CSS patch.")
        return Reply(f"AI returned {len(files)} web patch(es). Review before applying.", "stage_edits", {"edits":[{"file":k,"content":v} for k,v in files.items()]})

    @staticmethod
    def _name(prompt):
        m = re.search(r"(?:bikin|buat|generate|create|make)\s+(?:sebuah\s+)?(?:game\s+)?(.+)", prompt, re.I)
        return ((m.group(1) if m else prompt).strip(" .!?")[:60] or "HTML5 App")

    @staticmethod
    def _slug(name): return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "html5-app"
