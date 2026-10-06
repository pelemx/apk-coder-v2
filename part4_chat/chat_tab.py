"""
Chat Tab - context-aware chat for the JuprisX web/Android agent.

UI only. Language understanding lives in WebHybridEngine; project state in
ContextManager; actions go through ChatServices supplied by the app.
"""
from __future__ import annotations

import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    import tkinter as ctk
    USE_CTK = False

from part4_chat.context_manager import MODES, ContextManager
from part4_chat.web_hybrid_engine import WebHybridEngine, Reply


@dataclass
class ChatServices:
    scan: Optional[Callable[[], None]] = None
    keystore: Optional[Callable[[], None]] = None
    build: Optional[Callable[[], None]] = None
    stage_edits: Optional[Callable[[list], None]] = None
    create_project: Optional[Callable[[str, str, dict], dict]] = None
    attach_folder: Optional[Callable[[str], dict]] = None
    default_projects_dir: Optional[Callable[[], str]] = None
    open_assets: Optional[Callable[[], None]] = None
    setup_env: Optional[Callable[[], None]] = None
    auto_fix: Optional[Callable[[], None]] = None


class ChatTab:
    def __init__(self, parent_widget, context: ContextManager | None = None,
                 services: ChatServices | None = None):
        self.parent_widget = parent_widget
        self.ctx = context or ContextManager()
        self.services = services or ChatServices()
        self.engine = WebHybridEngine(self.ctx)
        self.engine_name = "Web Hybrid (HTML/JS + MCP)"
        self._queue: queue.Queue = queue.Queue()
        self._pending_project: dict[str, Any] | None = None
        self._busy = False

        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        Button = ctk.CTkButton if USE_CTK else ctk.Button
        Entry = ctk.CTkEntry if USE_CTK else ctk.Entry
        self.frame = Frame(parent_widget, corner_radius=8) if USE_CTK else Frame(parent_widget)
        Label(self.frame, text="Chat", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.status_lbl = Label(self.frame, text="", anchor="w", font=("Segoe UI", 10), justify="left", wraplength=480)
        self.status_lbl.pack(fill="x", padx=10, pady=(0, 4))
        mode_row = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        mode_row.pack(fill="x", padx=8, pady=2)
        self._mode_buttons: dict[str, Any] = {}
        for m in MODES:
            b = Button(mode_row, text=m, width=110, command=lambda mode=m: self.set_mode(mode)); b.pack(side="left", padx=2); self._mode_buttons[m] = b
        Button(mode_row, text="Attach Folder", width=110, command=self.attach_folder).pack(side="right", padx=2)
        if USE_CTK:
            self.history = ctk.CTkTextbox(self.frame, font=("Consolas", 12), wrap="word")
        else:
            from tkinter import scrolledtext
            self.history = scrolledtext.ScrolledText(self.frame, font=("Consolas", 12), wrap="word")
        self.history.pack(fill="both", expand=True, padx=8, pady=6)
        self.history.insert("end", "JuprisX Agent online. Contoh: halo | bikin game tebak warna | scan project | generate keystore | cek env\n\n")
        input_row = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame); input_row.pack(fill="x", padx=8, pady=(0, 10))
        self.entry = Entry(input_row, font=("Segoe UI", 12)); self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6)); self.entry.bind("<Return>", lambda e: self._send())
        self.send_btn = Button(input_row, text="Send", width=80, command=self._send); self.send_btn.pack(side="right")
        self._refresh_mode_buttons(); self.display_status(); self.frame.after(100, self._poll); threading.Thread(target=self._ping_bg, daemon=True).start()

    def set_mode(self, mode: str):
        if self.ctx.set_mode(mode):
            self._refresh_mode_buttons(); self.display_status()
            hint = {"General Chat": "diskusi bebas.", "Project Context": "AI melihat project aktif.", "New Project": "buat web app baru."}[mode]
            self.receive_message(f"[system] Mode: {mode} - {hint}")

    def set_project(self, project: dict | None):
        self.ctx.set_project(project)
        if project and self.ctx.mode == "General Chat": self.ctx.set_mode("Project Context"); self._refresh_mode_buttons()
        self.display_status()

    def set_working_dir(self, path: str):
        try: self.ctx.set_working_dir(path)
        except NotADirectoryError as exc: self.receive_message(str(exc)); return
        self.display_status()

    def display_status(self, engine: str | None = None, working_dir: str | None = None):
        if engine: self.engine_name = engine
        if working_dir: self.set_working_dir(working_dir); return
        link = "● MCP online" if self.engine.mcp_online else "○ MCP offline (local)"
        proj = self.ctx.project.get("name") if self.ctx.project else "-"
        self.status_lbl.configure(text=f"{link}  |  Engine: {self.engine_name}\nProject: {proj}  |  Dir: {self.ctx.active_working_dir or '(none)'}")

    def send_message(self, message: str):
        message = (message or "").strip()
        if not message: return
        self._append(f"You: {message}\n")
        if self._pending_project and self._handle_pending(message): return
        if self._busy: self.receive_message("Masih memproses pesan sebelumnya, tunggu sebentar."); return
        self._busy = True; self._set_sending(True); threading.Thread(target=self._worker, args=(message,), daemon=True).start()

    def receive_message(self, message: str): self._append(f"AI: {message}\n\n")

    def attach_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Pilih working directory project")
        if not folder: return
        if not self.services.attach_folder: self.set_working_dir(folder); return
        try: project = self.services.attach_folder(folder)
        except Exception as exc: self.receive_message(f"Gagal attach folder: {exc}"); return
        self.set_project(project); self.receive_message(f"Project **{project['name']}** aktif. Dir: {project['working_dir']}")

    def _worker(self, message: str):
        try: reply = self.engine.handle(message)
        except Exception as exc: reply = Reply(f"Error: {exc}")
        self._queue.put(reply)

    def _ping_bg(self): self.engine.ping(); self._queue.put(None)

    def _poll(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None: self.display_status()
                else:
                    self._busy = False; self._set_sending(False); self.receive_message(item.text); self.display_status(); self._run_action(item)
        except queue.Empty: pass
        self.frame.after(100, self._poll)

    def _run_action(self, reply: Reply):
        sv = self.services; mapping = {"scan": sv.scan, "keystore": sv.keystore, "build": sv.build, "assets": sv.open_assets, "setup_env": sv.setup_env, "auto_fix": sv.auto_fix}
        if reply.action in mapping:
            fn = mapping[reply.action]
            if fn: fn()
            else: self.receive_message(f"Aksi '{reply.action}' belum tersambung ke app.")
        elif reply.action == "stage_edits":
            if sv.stage_edits: sv.stage_edits(reply.data["edits"])
            else: self.receive_message("Reviewer belum tersambung.")
        elif reply.action == "create_project":
            self._pending_project = reply.data; self.ctx.set_mode("New Project"); self._refresh_mode_buttons(); self._pick_folder()

    def _pick_folder(self):
        from tkinter import filedialog
        initial = self.services.default_projects_dir() if self.services.default_projects_dir else None
        folder = filedialog.askdirectory(title="Simpan project di folder mana?", initialdir=initial, mustexist=False)
        if folder: self._create_in(folder)
        else: self.receive_message("Belum ada folder. Ketik *simpan di default*, ketik path folder, atau *batal*.")

    def _handle_pending(self, message: str) -> bool:
        low = message.lower()
        if re.search(r"\b(batal|cancel)\b", low): self._pending_project = None; self.receive_message("Dibatalkan. Project tidak disimpan."); return True
        if re.search(r"\b(default|workspace)\b", low):
            base = self.services.default_projects_dir() if self.services.default_projects_dir else None
            if not base: self.receive_message("Folder default belum tersedia, ketik path folder."); return True
            self._create_in(base, force_subfolder=True); return True
        candidate = Path(message.strip().strip('"')).expanduser()
        if candidate.is_absolute(): self._create_in(str(candidate)); return True
        return False

    def _create_in(self, folder: str, force_subfolder: bool = False):
        data = self._pending_project
        if not data: return
        if not self.services.create_project: self.receive_message("Penyimpanan project belum tersambung ke app."); return
        target = Path(folder).expanduser()
        if force_subfolder or (target.exists() and any(target.iterdir())): target = self._unique_dir(target / data.get("slug", "html5-app"))
        try: project = self.services.create_project(data["name"], str(target), data["files"])
        except Exception as exc: self.receive_message(f"Gagal menyimpan project: {exc}"); return
        self._pending_project = None; self.set_project(project); self.ctx.set_mode("Project Context"); self._refresh_mode_buttons(); self.display_status()
        self.receive_message(f"Project **{project['name']}** disimpan di `{project['working_dir']}` dan masuk Project Table. Ketik *scan project* untuk cek compatibility.")

    @staticmethod
    def _unique_dir(path: Path) -> Path:
        if not path.exists(): return path
        i = 2
        while (path.parent / f"{path.name}-{i}").exists(): i += 1
        return path.parent / f"{path.name}-{i}"

    def _append(self, text: str): self.history.insert("end", text); self.history.see("end")
    def _refresh_mode_buttons(self):
        for m, b in self._mode_buttons.items(): b.configure(text=("● " if m == self.ctx.mode else "") + m)
    def _set_sending(self, busy: bool):
        try: self.send_btn.configure(state="disabled" if busy else "normal")
        except Exception: pass
    def _send(self):
        msg = self.entry.get(); self.entry.delete(0, "end"); self.send_message(msg)
