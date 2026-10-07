"""HTML/JS aware chat engine layered over the existing MCP hybrid engine.

AI backends (config.json -> "llm_backend": "auto" | "bridge" | "mcp", default "auto"):
    bridge = POST {assets_api_url}/chat   (Python bridge, port 4333)
    mcp    = jupris_agentic_brain         (MCP server, port 3333)
"auto" tries the bridge first, then MCP.

Game generation never falls back silently to a canned template any more: when the
AI cannot produce a valid web project the user gets the reason and no project is
created (the old fallback was a math quiz, which looked like the AI ignored the request).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from .chat_api import ChatApiClient
from .hybrid_engine import HybridEngine, Reply

_LOG_DIR = Path(__file__).resolve().parent.parent / "workspace" / "logs"

_CUT_WORDS = r"\b(?:yang|dengan|dgn|dan|serta|untuk|supaya|agar|with|that|which|where|and|for|featuring)\b|[,.;:!?\n]"
_ASSET_KINDS = {"sprite", "background", "ui", "tile"}
_WEB_EXT = r"(?:html|css|js|json|svg|txt|md)"


class WebHybridEngine(HybridEngine):
    WEB_CONTRACT = """You are the code generator of an Android HTML5 app/game builder.
Generate a COMPLETE, PLAYABLE, offline-first web application that implements EXACTLY what the user asks.
STRICTLY use HTML5, CSS and JavaScript (Canvas allowed; Phaser only if bundled locally).

Required files: web/index.html, web/style.css, web/app.js
- Entry point is web/index.html; mobile viewport meta tag; touch + pointer + keyboard controls.
- Real game loop (requestAnimationFrame), start screen, score, game over + restart, responsive canvas (devicePixelRatio).
- All dependencies/assets are local relative files; never use CDN/http(s) resources.

IMAGES: the builder generates images for you.
- Reference them as relative PNG paths: assets/images/<name>.png  (name = lowercase a-z, 0-9, dash).
- Your code MUST still run if an image fails to load: draw a simple shape on the canvas instead (use img.onerror / complete checks).
- Also output ONE extra file `web/assets_needed.json` with a JSON array, max 6 items, e.g.
  [{"kind":"sprite","name":"car","prompt":"red sports race car, top view"},
   {"kind":"background","name":"road","prompt":"asphalt road with lane lines, top view"}]
  kind is one of: sprite | background | ui. Never output binary or base64 images.

OUTPUT FORMAT (strict): one fenced code block per file. The FIRST line inside each block is
`# file: web/<path>` (metadata only; it is removed automatically). No prose outside the blocks.
"""

    CHAT_PREAMBLE = (
        "Kamu adalah JuprisX Agent, asisten yang membuat game/app HTML5 (HTML+CSS+JS) lalu mem-build-nya "
        "menjadi APK/AAB Android lewat WebView. Jawab singkat dan jelas, dalam bahasa yang dipakai user. "
        "Jangan mengarang kemampuan lain.\n\nPesan user:\n"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chat_api = ChatApiClient(self.cfg)
        self.bridge_online = False
        self.llm_source = ""
        self._chat_id = self.chat_api.new_chat_id()
        self._chat_primed = False
        self.active_system_prompt = ""

    def set_persona(self, skill_name: str):
        if not getattr(self, "mcp_client", None) or not self.mcp_client.connected:
            return "MCP Client belum terkoneksi."
            
        skill_response = self.mcp_client.request(
            method="tools/call",
            params={
                "name": "jupris_load_skill",
                "arguments": {
                    "skill_name": skill_name
                }
            },
            timeout=10.0
        )
        
        if skill_response and "content" in skill_response and len(skill_response["content"]) > 0:
            self.active_system_prompt = skill_response["content"][0]["text"]
            return f"Skill {skill_name} berhasil dimuat."
        else:
            return f"Gagal memuat skill {skill_name}."

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------
    @property
    def ai_online(self) -> bool:
        return self.bridge_online or self.mcp_online

    def _backends(self) -> list[str]:
        mode = str(self.cfg.get("llm_backend", "auto")).lower()
        return {"bridge": ["bridge"], "mcp": ["mcp"]}.get(mode, ["bridge", "mcp"])

    def _call_llm(self, prompt: str, intent: str, timeout: float,
                  include_sources: bool = False, fresh: bool = False) -> Optional[str]:
        errors: list[str] = []
        for backend in self._backends():
            if backend == "bridge":
                if not self.chat_api.configured:
                    errors.append("bridge: belum dikonfigurasi")
                    continue
                if fresh:
                    cid, body = None, prompt
                else:
                    cid = self._chat_id
                    body = prompt if self._chat_primed else self.CHAT_PREAMBLE + prompt
                text = self.chat_api.ask(body, timeout=timeout, chat_id=cid)
                if text:
                    if not fresh:
                        self._chat_primed = True
                    self.bridge_online = True
                    self.llm_source = "bridge /chat"
                    self.last_error = ""
                    return text
                if "tidak bisa dihubungi" in self.chat_api.last_error:
                    self.bridge_online = False
                errors.append("bridge: " + (self.chat_api.last_error or "gagal"))
            else:
                text = self._call_mcp(prompt, intent, timeout, include_sources)
                if text:
                    self.llm_source = "MCP"
                    self.last_error = ""
                    return text
                errors.append("mcp: " + (self.last_error or "gagal"))
        self.last_error = " | ".join(errors)
        return None

    def _call_mcp(self, prompt: str, intent: str, timeout: float,
                  include_sources: bool = False) -> Optional[str]:
        if not getattr(self, "mcp_client", None) or not self.mcp_client.connected:
            self.last_error = "MCP Client offline"
            return None
            
        sys_prompt = self.active_system_prompt if self.active_system_prompt else self.WEB_CONTRACT
            
        res = self.mcp_client.request(
            method="tools/call",
            params={
                "name": "jupris_agentic_brain",
                "arguments": {
                    "prompt": prompt,
                    "intent": intent,
                    "system_prompt": sys_prompt
                }
            },
            timeout=timeout
        )
        
        if res and "content" in res and len(res["content"]) > 0:
            return res["content"][0]["text"]
            
        self.last_error = self.mcp_client.last_error or "Empty response dari MCP brain"
        return None

    def ping(self, timeout: float = 4.0) -> bool:
        if self.chat_api.configured:
            self.bridge_online = self.chat_api.ping(timeout)
        mcp_ok = False
        if "mcp" in self._backends() or not self.bridge_online:
            mcp_ok = super().ping(timeout)
        return self.bridge_online or mcp_ok

    def diagnose(self) -> str:
        lines = ["**Cek koneksi AI**", f"- Urutan backend: {' -> '.join(self._backends())}"]
        if self.chat_api.configured:
            ok, raw = self.chat_api.models()
            lines.append(f"- Bridge {self.chat_api.url} /models: {'OK' if ok else 'GAGAL'} - {raw[:160]}")
            started = time.monotonic()
            text = self.chat_api.ask("Balas dengan satu kata saja: OK", timeout=45, chat_id=self.chat_api.new_chat_id())
            took = time.monotonic() - started
            self.bridge_online = bool(text) or ok
            if text:
                lines.append(f"- Bridge /chat: OK ({took:.1f}s) - balasan: {text[:120]!r}")
            else:
                lines.append(f"- Bridge /chat: GAGAL - {self.chat_api.last_error}")
            if self.chat_api.last_raw:
                lines.append(f"- Raw /chat (HTTP {self.chat_api.last_status}): {self.chat_api.last_raw[:300]}")
        else:
            lines.append("- Bridge: belum dikonfigurasi (isi assets_api_url di config.json)")
        lines.append("")
        lines.append(HybridEngine.diagnose(self))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Intent
    # ------------------------------------------------------------------
    @staticmethod
    def extract_game_name(prompt: str) -> str:
        m = re.search(r"(?:bikin\w*|buat\w*|generate|create|make)\s+(?:sebuah\s+|a\s+)?(?:game\s+|permainan\s+)?(.+)", prompt, re.I | re.S)
        raw = (m.group(1) if m else prompt)
        raw = re.split(_CUT_WORDS, raw, maxsplit=1, flags=re.I)[0]
        raw = re.sub(r"^(game|pygame|permainan)\s+", "", raw.strip(), flags=re.I)
        words = re.sub(r"[^\w\s\-]", " ", raw).split()
        if len(words) > 1 and words[-1].lower() in ("game", "permainan"):
            words.pop()
        name = " ".join(words[:4])
        return name[:60] or "HTML5 Game"

    def detect_action(self, prompt: str) -> str:
        p = prompt.lower().strip()
        if re.search(r"\b(cek|check|test|tes)\s+(api|chat|ai|llm|bridge)\b", p):
            return "check_mcp"
        make_game = re.search(r"\b(bikin\w*|buat\w*|generate|create|make|tulis\w*|coding\w*)\b", p)
        if make_game and (re.search(r"\b(game|pygame|permainan)\b", p) or "tebak" in p or "snake" in p):
            return "generate_game"
        return super().detect_action(prompt)

    @staticmethod
    def _slug_web(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "html5-app"

    # ------------------------------------------------------------------
    # Parsing / validation of AI output
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(files: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for path, content in files.items():
            p = str(path).strip().replace("\\", "/")
            p = re.sub(r"^(\./)+", "", p).lstrip("/")
            if not p or ".." in p.split("/"):
                continue
            if not p.startswith("web/"):
                p = "web/" + p
            out[p] = content
        return out

    @staticmethod
    def _files_from_json(text: str) -> dict[str, str]:
        decoder = json.JSONDecoder()
        for m in re.finditer(r"\{", text):
            try:
                obj, _ = decoder.raw_decode(text[m.start():])
            except ValueError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("files"), list):
                files = {f["path"]: f["content"] for f in obj["files"]
                         if isinstance(f, dict) and f.get("path") and isinstance(f.get("content"), str)}
                if files:
                    return files
        return {}

    @staticmethod
    def _files_from_headings(text: str) -> dict[str, str]:
        files: dict[str, str] = {}
        pos = 0
        for m in re.finditer(r"```([^\n`]*)\n(.*?)```", text, re.S):
            before = text[pos:m.start()].strip().splitlines()
            pos = m.end()
            if not before:
                continue
            hit = re.search(rf"([\w./-]+\.{_WEB_EXT})\b", before[-1])
            if hit:
                body = m.group(2)
                files[hit.group(1)] = body if body.endswith("\n") else body + "\n"
        return files

    @staticmethod
    def _single_page(text: str) -> dict[str, str]:
        blocks = [(m.group(1).strip().lower(), m.group(2)) for m in re.finditer(r"```([^\n`]*)\n(.*?)```", text, re.S)]
        html = [b for lang, b in blocks if lang.startswith("html") and re.search(r"<!doctype|<html", b, re.I)]
        if len(html) != 1:
            return {}
        files = {"web/index.html": html[0]}
        css = [b for lang, b in blocks if lang == "css"]
        js = [b for lang, b in blocks if lang in ("js", "javascript")]
        if len(css) == 1 and "style.css" in html[0]:
            files["web/style.css"] = css[0]
        if len(js) == 1 and "app.js" in html[0]:
            files["web/app.js"] = js[0]
        return files

    @classmethod
    def parse_web_files(cls, text: str) -> dict[str, str]:
        files = cls.parse_files(text)
        for finder in (cls._files_from_json, cls._files_from_headings, cls._single_page):
            if files:
                break
            files = finder(text)
        return cls._normalize(files)

    def _parse_web_response(self, text: str) -> dict[str, str]:
        files = self.parse_web_files(text)
        if "web/index.html" not in files:
            return {}
        return files

    @classmethod
    def _validate_generated(cls, files: dict[str, str]) -> str:
        if not files:
            return "balasan AI tidak berisi file (format `# file: web/...` tidak ditemukan)"
        html = files.get("web/index.html")
        if html is None:
            return "web/index.html tidak ada"
        if not re.search(r"<script", html, re.I):
            return "index.html tidak memuat JavaScript (<script>)"
        if re.search(r"<(?:script|link)[^>]+(?:src|href)\s*=\s*[\"']https?://", html, re.I):
            return "index.html memakai CDN/URL eksternal"
        code = sum(len(v) for k, v in files.items() if k.endswith((".js", ".html")))
        if code < 600:
            return "kode terlalu pendek untuk sebuah game"
        return ""

    @staticmethod
    def _pop_assets_needed(files: dict[str, str]) -> list[dict[str, str]]:
        raw = files.pop("web/assets_needed.json", None)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except ValueError:
            return []
        items = data.get("assets", []) if isinstance(data, dict) else data
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind", "sprite")).lower()
            name = re.sub(r"[^a-z0-9]+", "-", str(it.get("name", "")).lower()).strip("-")
            prompt = str(it.get("prompt", "")).strip()
            if kind not in _ASSET_KINDS or not name or not prompt or name in seen:
                continue
            seen.add(name)
            out.append({"kind": kind, "name": name, "prompt": prompt[:300]})
            if len(out) >= 6:
                break
        return out

    @staticmethod
    def _save_log(name: str, sections: list[tuple[str, str]]) -> str:
        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = _LOG_DIR / "last_generation.txt"
            body = [f"# generation: {name}  ({time.strftime('%Y-%m-%d %H:%M:%S')})"]
            for title, text in sections:
                body.append(f"\n===== {title} =====\n{text}")
            path.write_text("\n".join(body), encoding="utf-8")
            return str(path)
        except OSError:
            return ""

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def _do_generate(self, prompt: str) -> Reply:
        name = self.extract_game_name(prompt)
        request = self.WEB_CONTRACT + "\nUSER REQUEST (implement exactly this):\n" + prompt.strip()
        sections: list[tuple[str, str]] = []
        files: dict[str, str] = {}
        reason = ""

        for attempt in (1, 2):
            req = request
            if attempt == 2:
                req += (f"\n\nINVALID PREVIOUS RESPONSE: {reason}. Discard it completely. "
                        "Return ONLY the complete HTML/CSS/JS project in the strict file-block format.")
            text = self._call_llm(req, "ask_guidance", self.cfg["mcp_timeout_generate"],
                                  include_sources=False, fresh=True)
            if not text:
                reason = self.last_error or "tidak ada balasan dari server AI"
                sections.append((f"attempt {attempt}: NO REPLY", reason))
                break
            sections.append((f"attempt {attempt}: raw reply ({self.llm_source})", text))
            files = self.parse_web_files(text)
            reason = self._validate_generated(files)
            if not reason:
                break
            sections.append((f"attempt {attempt}: rejected", reason))
            files = {}

        log_path = self._save_log(name, sections)
        if not files:
            hint = f"\nLog lengkap: `{log_path}`" if log_path else ""
            return Reply(
                f"Gagal membuat **{name}**: {reason}.\n"
                "Project TIDAK dibuat (aku tidak lagi memakai template kuis penjumlahan sebagai pengganti).\n"
                f"Ketik **cek api** untuk diagnosa koneksi AI, lalu ulangi perintahnya.{hint}")

        assets_needed = self._pop_assets_needed(files)
        extra = ("\nIcon app + gambar game akan digenerate otomatis setelah project disimpan."
                 if self.cfg.get("auto_assets", True) else "")
        return Reply(
            f"Web app **{name}** siap (sumber: {self.llm_source}). File: {', '.join(sorted(files))}.{extra}\n"
            "Mau simpan di folder mana? Pilih folder, atau ketik *simpan di default*.",
            action="create_project",
            data={"name": name.title(), "slug": self._slug_web(name), "files": files,
                  "source": self.llm_source, "assets_needed": assets_needed,
                  "description": prompt.strip()[:140]},
        )

    def make_fix_provider(self):
        def provider(prompt: str) -> dict:
            text = self._call_llm(self.WEB_CONTRACT + "\nFix only these findings:\n" + prompt, "request_patch",
                                  self.cfg["mcp_timeout_generate"], include_sources=True, fresh=True)
            if not text:
                return {}
            files = self.parse_web_files(text)
            files.pop("web/assets_needed.json", None)
            return files
        return provider

    # ------------------------------------------------------------------
    # Other actions (unchanged behaviour)
    # ------------------------------------------------------------------
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
        return ("**JuprisX Web App Builder**\n\n- Generate: `bikin game race car drift` / `bikin game tebak warna`\n- Scan: `scan project`\n- Auto-fix: `auto fix`\n- Keystore: `generate keystore`\n- Build: `compile apk` / `build aab`\n- Assets: `generate icon` (panel) - icon + gambar game juga digenerate otomatis saat project dibuat\n- Environment: `cek env`\n- Koneksi AI: `cek api` / `cek mcp`\n\nGenerated apps use HTML5 + CSS + JavaScript inside the native Android WebView container.")