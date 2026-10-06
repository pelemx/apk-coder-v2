"""HTML/JS aware chat engine layered over the existing MCP hybrid engine."""
from __future__ import annotations

import re
from .hybrid_engine import HybridEngine, Reply
from .templates import build_template


class WebHybridEngine(HybridEngine):
    WEB_CONTRACT = """Generate an Android-ready offline-first web application.
STRICTLY use HTML5, CSS and JavaScript (Canvas/Phaser allowed when bundled locally).
Do NOT generate Python, Pygame, pygame-ce, SDL2, Buildozer or python-for-android.
Entry point must be web/index.html. All dependencies/assets must be local relative files;
never use CDN/http resources. Include a mobile viewport meta tag and touch-friendly controls.
Return JSON {files:[{path,content}]} using paths under web/.
"""

    _LEGACY_MARKERS = (
        "pygame", "pygame-ce", "python-for-android", "buildozer",
        "pip install pygame", "pip install pygame-ce", "import pygame",
    )

    @staticmethod
    def extract_game_name(prompt: str) -> str:
        m = re.search(r"(?:bikin|buat|generate|create|make)\s+(?:sebuah\s+)?(?:game\s+)?(.+)", prompt, re.I)
        name = (m.group(1) if m else prompt).strip(" .!?")
        name = re.sub(r"^(game|pygame)\s+", "", name, flags=re.I)
        return name[:60] or "HTML5 Game"

    def detect_action(self, prompt: str) -> str:
        """Give web-game generation precedence over all environment/build actions."""
        p = prompt.lower().strip()
        make_game = re.search(r"\b(bikin\w*|buat\w*|generate|create|make|tulis\w*|coding\w*)\b", p)
        if make_game and (re.search(r"\b(game|pygame|permainan)\b", p) or "tebak" in p or "snake" in p):
            return "generate_game"
        return super().detect_action(prompt)

    @staticmethod
    def _slug_web(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "html5-app"

    @classmethod
    def _is_legacy_output(cls, files: dict[str, str]) -> bool:
        for path, content in files.items():
            if path.lower().endswith((".py", ".pyw")):
                return True
            sample = str(content).lower()
            if any(marker in sample for marker in cls._LEGACY_MARKERS):
                return True
        return False

    def _parse_web_response(self, text: str) -> dict[str, str]:
        parsed = self.parse_files(text)
        files = {k if k.startswith("web/") else "web/" + k: v for k, v in parsed.items()}
        if self._is_legacy_output(files) or "web/index.html" not in files:
            return {}
        return files

    def _do_generate(self, prompt: str) -> Reply:
        name = self.extract_game_name(prompt)
        files, source = {}, "template lokal"
        request = self.WEB_CONTRACT + "\nUser request:\n" + prompt
        text = self._call_mcp(request, "ask_guidance", timeout=self.cfg["mcp_timeout_generate"], include_sources=False)
        if text:
            files = self._parse_web_response(text)

        # MCP/provider may still return the retired Pygame contract. Never let that
        # payload reach create_project: retry once with an explicit correction, then
        # fall back to the known-good HTML template.
        if not files and text:
            retry = (
                self.WEB_CONTRACT
                + "\nINVALID PREVIOUS RESPONSE: it contained Python/Pygame or did not contain web/index.html."
                + "\nDiscard it completely. Return ONLY a complete HTML/CSS/JS web project."
                + "\nUser request:\n" + prompt
            )
            retry_text = self._call_mcp(retry, "ask_guidance", timeout=self.cfg["mcp_timeout_generate"], include_sources=False)
            if retry_text:
                files = self._parse_web_response(retry_text)

        if files:
            source = "MCP / Jupris"
        else:
            files = build_template(name)

        return Reply(
            f"Web app **{name}** siap ({source}). File: {', '.join(sorted(files))}.\nMau simpan di folder mana? Pilih folder, atau ketik *simpan di default*.",
            action="create_project",
            data={"name": name.title(), "slug": self._slug_web(name), "files": files, "source": source},
        )

    def make_fix_provider(self):
        def provider(prompt: str) -> dict:
            text = self._call_mcp(self.WEB_CONTRACT + "\nFix only these findings:\n" + prompt, "request_patch", timeout=self.cfg["mcp_timeout_generate"], include_sources=True)
            if not text: return {}
            files = {k if k.startswith("web/") else "web/" + k: v for k, v in self.parse_files(text).items()}
            if self._is_legacy_output(files):
                return {}
            return files
        return provider

    def _do_check_env(self, _prompt: str) -> Reply:
        from part1_builder.wsl_checker import check_wsl_environment
        env = check_wsl_environment(); mark = lambda ok: "OK" if ok else "MISSING"
        return Reply("\n".join(["**Android Web build environment** (native Gradle)", f"- JDK/keytool: {mark(env.get('jdk_available'))}", f"- Gradle: {mark(env.get('gradle_available'))}", f"- Android SDK: {mark(env.get('android_sdk'))}", "- Buildozer: NOT USED", "- Pygame: NOT USED"]))

    def _do_setup_env(self, _prompt: str) -> Reply:
        return Reply("Checking native Android build environment (JDK, Android SDK, Gradle, keytool).", action="setup_env")

    def _do_fix(self, prompt: str) -> Reply:
        if (r := self._need_project()): return r
        findings = self.ctx.project.get("findings", []) if self.ctx.project else []
        if not findings: return Reply("Tidak ada findings. Jalankan scan project dulu.")
        return Reply("Menyiapkan web-only patch untuk findings project. Perubahan akan masuk Reviewer.", action="auto_fix")

    def _help_text(self) -> str:
        return ("**JuprisX Web App Builder**\n\n- Generate: `make simple game math` / `bikin game tebak warna`\n- Scan: `scan project`\n- Auto-fix: `auto fix`\n- Keystore: `generate keystore`\n- Build: `compile apk` / `build aab`\n- Assets: `generate icon`\n- Environment: `cek env`\n\nGenerated apps use HTML5 + CSS + JavaScript inside the native Android WebView container.")
