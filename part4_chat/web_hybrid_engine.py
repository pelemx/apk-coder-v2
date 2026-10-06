"""HTML/JS aware chat engine layered over the existing MCP hybrid engine."""
from __future__ import annotations

import re
from .hybrid_engine import HybridEngine, Reply
from .templates import build_template


class WebHybridEngine(HybridEngine):
    WEB_CONTRACT = """Generate an Android-ready offline-first web application.
STRICTLY use HTML5, CSS and JavaScript (Canvas/Phaser allowed when bundled locally).
Do NOT generate Python, Pygame, pygame-ce, SDL2, Buildozer or python-for-android.
Entry point must be index.html at project root. All dependencies/assets must be local
relative files; never use CDN/http resources. Include a mobile viewport meta tag and
touch-friendly controls. Return JSON {files:[{path,content}]}.
"""

    @staticmethod
    def extract_game_name(prompt: str) -> str:
        m = re.search(r"(?:bikin|buat|generate|create|make)\s+(?:sebuah\s+)?(?:game\s+)?(.+)", prompt, re.I)
        name = (m.group(1) if m else prompt).strip(" .!?")
        name = re.sub(r"^(game|pygame)\s+", "", name, flags=re.I)
        return name[:60] or "HTML5 Game"

    @staticmethod
    def _slug_web(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "html5-app"

    def _do_generate(self, prompt: str) -> Reply:
        name = self.extract_game_name(prompt)
        files, source = {}, "template lokal"
        text = self._call_mcp(self.WEB_CONTRACT + "\nUser request:\n" + prompt,
                              "ask_guidance", timeout=self.cfg["mcp_timeout_generate"], include_sources=False)
        if text:
            files = {k: v for k, v in self.parse_files(text).items()
                     if not k.lower().endswith((".py", ".pyw"))}
            if "index.html" in files:
                source = "MCP / Jupris"
            else:
                files = {}
        if not files:
            files = build_template(name)
        return Reply(
            f"Web app **{name}** siap ({source}). File: {', '.join(sorted(files))}.\nMau simpan di folder mana? Pilih folder, atau ketik *simpan di default*.",
            action="create_project",
            data={"name": name.title(), "slug": self._slug_web(name), "files": files, "source": source},
        )

    def _do_check_env(self, _prompt: str) -> Reply:
        from part1_builder.wsl_checker import check_wsl_environment
        env = check_wsl_environment()
        mark = lambda ok: "OK" if ok else "MISSING"
        return Reply("\n".join([
            "**Android Web build environment** (Windows-native Gradle)",
            f"- JDK/keytool: {mark(env.get('jdk_available'))}",
            f"- Gradle: {mark(env.get('gradle_available'))}",
            f"- Android SDK: {mark(env.get('android_sdk'))}",
            "- Buildozer: NOT USED",
            "- Pygame: NOT USED",
        ]))

    def _do_setup_env(self, _prompt: str) -> Reply:
        return Reply("Checking native Android build environment (JDK, Android SDK, Gradle, keytool).", action="setup_env")

    def _help_text(self) -> str:
        return ("**JuprisX Web App Builder**\n\n"
                "- Generate: `make simple game math` / `bikin game tebak warna`\n"
                "- Scan: `scan project`\n- Auto-fix: `auto fix`\n"
                "- Keystore: `generate keystore`\n- Build: `compile apk` / `build aab`\n"
                "- Assets: `generate icon`\n- Environment: `cek env`\n\n"
                "Generated apps use HTML5 + CSS + JavaScript inside the native Android WebView container.")
