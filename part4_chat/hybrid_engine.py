"""
Hybrid Chat Engine for JuprisX.

    Intent.SIMPLE   -> local rules (instant)
    Intent.COMPLEX  -> MCP (jupris_agentic_brain) when online, local fallback otherwise
    Intent.TOOL     -> executed through the app (scan / keystore / build) or locally (env check)

The engine is UI-free and blocking: ChatTab calls handle() from a worker thread.
It never writes project files itself; it returns a Reply whose `action` the app
carries out (so Approve/Reject in the Reviewer stays the only way to patch code).
"""
from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .context_manager import ContextManager
from .mcp_client import McpClient
from .templates import build_template

try:
    import requests
    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    HAS_REQUESTS = False

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


class Intent(str, Enum):
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"
    TOOL = "TOOL"


@dataclass
class Reply:
    text: str
    action: Optional[str] = None   # scan | keystore | build | create_project | stage_edits
    data: dict[str, Any] = field(default_factory=dict)


def load_config(path: Path = _CONFIG_PATH) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "mcp_url": "", "mcp_api_key": "",
        "mcp_timeout_chat": 8, "mcp_timeout_generate": 90,
    }
    try:
        cfg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    # environment wins over file
    cfg["mcp_url"] = os.environ.get("JUPRISX_MCP_URL", cfg["mcp_url"])
    cfg["mcp_api_key"] = os.environ.get("JUPRISX_MCP_KEY", cfg["mcp_api_key"])
    return cfg


def _has(p: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", p) for w in words)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "pygame-game"


class HybridEngine:
    def __init__(self, context: ContextManager | None = None,
                 config: dict[str, Any] | None = None):
        self.ctx = context or ContextManager()
        self.cfg = config if config is not None else load_config()
        self.history: list[tuple[str, str]] = []
        self.mcp_online: bool = False
        self.last_error: str = ""
        self.mcp = McpClient(self.cfg)

    # ------------------------------------------------------------------
    # Intent detection
    # ------------------------------------------------------------------
    def detect_action(self, prompt: str) -> str:
        p = prompt.lower().strip()
        if _has(p, "keystore"):
            return "keystore"
        if re.search(r"\b(setup|install|siapkan|perbaiki|repair|fix)\s+(wsl|env|environment|buildozer)|\bauto\s*setup", p):
            return "setup_env"
        if re.search(r"\bauto\s*-?\s*fix|\bfix\s+otomatis|\bloop\s+fix|\bperbaiki\s+otomatis", p):
            return "auto_fix"
        if re.search(r"\b(cek|check|test|tes)\s+(mcp|server|koneksi|connection)\b", p):
            return "check_mcp"
        if re.search(r"\bcek\s+env|\bcheck\s+(env|wsl)|\bwsl\b|\benvironment\b", p):
            return "check_env"
        if _has(p, "icon", "assets", "asset", "screenshot") or "feature graphic" in p or "playstore" in p:
            return "assets"
        if _has(p, "compile", "buildozer", "apk", "aab", "build", "release"):
            return "build"
        if _has(p, "scan", "analisis", "analyze", "agentic"):
            return "scan"
        if _has(p, "fix", "patch", "perbaiki", "benerin", "compatible"):
            return "fix"
        make_verb = re.search(r"\b(bikin\w*|buat\w*|generate|create|make|tulis\w*|coding\w*)\b", p)
        if make_verb and (_has(p, "game", "pygame", "permainan") or "tebak" in p or "snake" in p):
            return "generate_game"
        if _has(p, "help", "bantuan", "fitur") or "cara pakai" in p:
            return "help"
        return "chat"

    def detect_intent(self, prompt: str) -> Intent:
        action = self.detect_action(prompt)
        if action in ("keystore", "check_env", "build", "scan", "assets", "setup_env", "auto_fix", "check_mcp"):
            return Intent.TOOL
        if action in ("fix", "generate_game"):
            return Intent.COMPLEX
        return Intent.SIMPLE

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def handle(self, prompt: str) -> Reply:
        prompt = prompt.strip()
        action = self.detect_action(prompt)
        handler = {
            "check_env": self._do_check_env,
            "check_mcp": lambda _p: Reply(self.diagnose()),
            "setup_env": self._do_setup_env,
            "auto_fix": self._do_auto_fix,
            "scan": self._do_scan,
            "keystore": self._do_keystore,
            "build": self._do_build,
            "assets": self._do_assets,
            "fix": self._do_fix,
            "generate_game": self._do_generate,
            "help": lambda _p: Reply(self._help_text()),
        }.get(action, self._do_chat)
        reply = handler(prompt)
        self.history.append(("user", prompt))
        self.history.append(("ai", reply.text))
        return reply

    # ------------------------------------------------------------------
    # TOOL actions
    # ------------------------------------------------------------------
    def _need_project(self) -> Optional[Reply]:
        if self.ctx.has_project:
            return None
        return Reply("Belum ada project aktif. Pilih satu di Project Table, "
                     "tekan **Attach Folder**, atau mulai dengan *bikin game ...*.")

    def _do_check_env(self, _prompt: str) -> Reply:
        from part1_builder.wsl_checker import check_wsl_environment
        env = check_wsl_environment()
        mark = lambda ok: "OK " if ok else "MISSING"  # noqa: E731
        lines = [
            "**Environment check** (build environment: " + env.get("mode", "?") + ")",
            f"- WSL: {mark(env['is_wsl'])}",
            f"- Python: {env['python_version'] or 'MISSING'}",
            f"- pygame: {mark(env['pygame_installed'])}",
            f"- JDK: {mark(env['jdk_available'])}",
            f"- Buildozer: {mark(env['buildozer_available'])}",
            f"- Android SDK (downloaded on first build): {mark(env['android_sdk'])}",
        ]
        if env.get("missing_apt"):
            lines.append("- apt belum terpasang: " + ", ".join(env["missing_apt"]))
        if env["errors"]:
            lines.append("\nCatatan: " + "; ".join(env["errors"]))
        if not env.get("ready"):
            lines.append("\nKetik **setup wsl** supaya agent memperbaikinya sendiri.")
        return Reply("\n".join(lines))

    def _do_setup_env(self, _prompt: str) -> Reply:
        return Reply("Menyiapkan build environment di WSL (apt packages, Buildozer, pygame). "
                     "Ini bisa makan beberapa menit; progres tampil di Log.", action="setup_env")

    def _do_auto_fix(self, _prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        return Reply(f"Menjalankan loop fix -> validate -> re-scan untuk **{self.ctx.project['name']}** "
                     "(maks 3 percobaan, semua perubahan di-backup dan bisa di-rollback).", action="auto_fix")

    def make_fix_provider(self):
        """Callable for AgentClient: prompt -> {relative_path: new_content} from the MCP coder."""
        def provider(prompt: str) -> dict:
            text = self._call_mcp(prompt, "request_patch", timeout=self.cfg["mcp_timeout_generate"],
                                  include_sources=True)
            return self.parse_files(text) if text else {}
        return provider

    def _do_scan(self, _prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        return Reply(f"Scanning **{self.ctx.project['name']}** ...", action="scan")

    def _do_keystore(self, _prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        return Reply("Siapkan keystore release. Isi alias & password di dialog yang muncul. "
                     "Keystore tidak boleh hilang - satu keystore untuk semua update Play Store.",
                     action="keystore")

    def _do_assets(self, _prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        return Reply("Membuka panel **Play Store Assets** (icon 512x512, feature graphic 1024x500, "
                     "screenshot).", action="assets")

    def _do_build(self, _prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        return Reply(f"Memulai build **{self.ctx.project['name']}** ...", action="build")

    # ------------------------------------------------------------------
    # COMPLEX actions
    # ------------------------------------------------------------------
    @staticmethod
    def extract_game_name(prompt: str) -> str:
        m = re.search(r"(?:bikin|buat|generate|create|make)\s+(?:sebuah\s+)?(?:game\s+)?(?:pygame\s+)?(.+)",
                      prompt, re.I)
        name = (m.group(1) if m else prompt).strip(" .!?")
        name = re.sub(r"^(game|pygame)\s+", "", name, flags=re.I)
        return name[:60] or "Pygame Game"

    def _do_generate(self, prompt: str) -> Reply:
        name = self.extract_game_name(prompt)
        files: dict[str, str] = {}
        source = "template lokal"

        text = self._call_mcp(
            prompt + "\n\nReturn complete project files. Format each file as a fenced code "
                     "block whose first line is `# file: relative/path.py`.",
            "ask_guidance", timeout=self.cfg["mcp_timeout_generate"])
        if text:
            files = self.parse_files(text)
            if files:
                source = "MCP / Jupris"
        if not files:
            files = build_template(name)

        listing = ", ".join(sorted(files))
        return Reply(
            f"Game **{name}** siap ({source}). File: {listing}.\n"
            "Mau simpan di folder mana? Pilih folder, atau ketik *simpan di default*.",
            action="create_project",
            data={"name": name.title(), "slug": slugify(name), "files": files, "source": source},
        )

    def _do_fix(self, prompt: str) -> Reply:
        if (r := self._need_project()):
            return r
        project = self.ctx.project or {}
        findings = project.get("findings", [])
        if not findings:
            return Reply("Tidak ada findings di project ini. Jalankan **scan** dulu kalau mau cek ulang.")

        text = self._call_mcp(
            prompt + "\n\nFix ONLY the listed findings with minimal edits. Return the full updated "
                     "content of each changed file as a fenced block whose first line is "
                     "`# file: relative/path.py`.",
            "request_patch", timeout=self.cfg["mcp_timeout_generate"], include_sources=True)
        files = self.parse_files(text) if text else {}
        if files:
            edits = [{"file": k, "content": v} for k, v in files.items()]
            return Reply(f"Dapat {len(edits)} patch dari AI. Cek diff di panel Reviewer, "
                         "lalu **Approve** atau **Reject**. Belum ada file yang diubah.",
                         action="stage_edits", data={"edits": edits})

        plan = project.get("plan", [])
        steps = "\n".join(f"- {s['file']}:{s['line']} - {s['action']}" for s in plan[:10]) or "-"
        why = (f"Server AI tidak merespons ({self.last_error})." if not text
               else "Respons AI tidak berisi file patch.")
        return Reply(f"{why} Auto-fix butuh MCP online. Rencana perbaikan saat ini:\n{steps}")

    def _do_chat(self, prompt: str) -> Reply:
        p = prompt.lower()
        if _has(p, "halo", "hai", "hi", "hello", "hey"):
            return Reply(
                "Halo! Aku JuprisX Agent.\n" + self.ctx.status_line() + "\n\n"
                "Bisa: bikin game pygame, scan/fix project, generate keystore, "
                "build APK/AAB, cek env. Ketik *help* untuk contoh.")
        if _has(p, "status") or "lagi apa" in p:
            return Reply(self.ctx.status_line() + f" | MCP: {'online' if self.mcp_online else 'offline'}")
        if "jam berapa" in p or "jam sekarang" in p:
            return Reply("Sekarang " + datetime.datetime.now().strftime("%A, %d %B %Y %H:%M"))
        if _has(p, "mode"):
            return Reply(f"Mode chat aktif: **{self.ctx.mode}**. Ganti lewat tombol di atas chat.")

        # General discussion: use the AI server if reachable.
        text = self._call_mcp(prompt, "ask_guidance", timeout=self.cfg["mcp_timeout_chat"],
                              include_sources=self.ctx.mode == "Project Context")
        if text:
            return Reply(text)
        reason = f"\nAlasan: {self.last_error}" if self.last_error else ""
        return Reply("Server AI tidak bisa dipakai, jadi aku hanya bisa perintah lokal "
                     "(scan, fix, keystore, build, cek env). Ketik **cek mcp** untuk diagnosa." + reason)

    # ------------------------------------------------------------------
    # MCP
    # ------------------------------------------------------------------
    def ping(self, timeout: float = 4.0) -> bool:
        """Real check: can we complete an MCP handshake? Sets last_error when not."""
        self.mcp_online = self.mcp.connect(timeout)
        self.last_error = "" if self.mcp_online else self.mcp.last_error
        return self.mcp_online

    def diagnose(self) -> str:
        self.ping(timeout=6.0)
        return "\n".join(["**MCP check**"] + self.mcp.describe())

    def _call_mcp(self, prompt: str, intent: str, timeout: float,
                  include_sources: bool = False) -> Optional[str]:
        data = self.mcp.request("tools/call", {
            "name": "jupris_agentic_brain",
            "arguments": {"prompt": prompt, "intent": intent,
                          "context": self.ctx.build_context(include_sources=include_sources)},
        }, timeout)
        if data is None:
            self.mcp_online = False
            self.last_error = self.mcp.last_error
            return None
        self.mcp_online = True
        text = self.parse_mcp_response(data)
        if text is None:
            self.last_error = "Server menjawab tapi tanpa teks / format salah."
        return text

    @staticmethod
    def parse_mcp_response(data: Any) -> Optional[str]:
        """Handle JSON-RPC results incl. MCP `content: [{type:'text', text:...}]`."""
        if not isinstance(data, dict):
            return None
        if data.get("error"):
            return None
        res = data.get("result", data)
        if isinstance(res, str):
            return res or None
        if isinstance(res, dict):
            if res.get("isError"):
                return None
            content = res.get("content")
            if isinstance(content, list):
                parts = [c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type", "text") == "text"]
                text = "\n".join(p for p in parts if p).strip()
                return text or None
            if isinstance(content, str):
                return content or None
            for key in ("message", "text", "response"):
                if isinstance(res.get(key), str) and res[key]:
                    return res[key]
        return None

    @staticmethod
    def parse_files(text: str) -> dict[str, str]:
        """Extract {relative_path: content} from an AI reply.

        Accepts (1) JSON {"files":[{"path","content"}]}, or fenced blocks where the
        path is given by a first line `# file: x.py` / `// file: x` or by the fence
        info string (```python:x.py or ```python file=x.py).
        Paths are validated later by ProjectManager / Fixer.
        """
        files: dict[str, str] = {}
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
                for f in obj.get("files", []):
                    if isinstance(f, dict) and f.get("path") and isinstance(f.get("content"), str):
                        files[f["path"]] = f["content"]
                if files:
                    return files
            except json.JSONDecodeError:
                pass

        for m in re.finditer(r"```([^\n`]*)\n(.*?)```", text, re.S):
            info, body = m.group(1).strip(), m.group(2)
            path = None
            mi = re.search(r"(?:file=|:)\s*([\w./\\-]+\.\w+)\s*$", info)
            if mi:
                path = mi.group(1)
            else:
                first, _, rest = body.partition("\n")
                mh = re.match(r"^\s*(?:#|//|<!--)\s*file:\s*([\w./\\-]+)", first)
                if mh:
                    path, body = mh.group(1), rest
            if path:
                files[path.replace("\\", "/")] = body if body.endswith("\n") else body + "\n"
        return files

    # ------------------------------------------------------------------
    def _help_text(self) -> str:
        return (
            "**JuprisX Chat - cara pakai**\n\n"
            "- Generate game: `bikin game pygame tebak warna`\n"
            "- Scan: `scan project`\n"
            "- Fix: `fix project biar compatible builder` (patch muncul di Reviewer)\n"
            "- Keystore: `generate keystore`\n"
            "- Build: `compile apk`\n"
            "- Env: `cek env`\n"
            "- Asset Play Store: `bikin icon`\n\n"
            "Mode: **General Chat** (diskusi bebas), **Project Context** (terikat project aktif), "
            "**New Project** (generate project baru dari chat)."
        )