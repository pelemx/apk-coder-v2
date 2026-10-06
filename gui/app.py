"""JuprisX HTML/JS Android Builder desktop GUI."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    USE_CTK = True
except ImportError:
    import tkinter as ctk
    USE_CTK = False

from part3_project.project_manager import ProjectManager
from part3_project.project_table import ProjectTable
from part3_project.reviewer import ReviewerPanel
from part3_project.workflow import InvalidTransition
from part4_chat.chat_tab import ChatServices, ChatTab
from part4_chat.context_manager import ContextManager


class TextPanel:
    def __init__(self, parent, title: str, height: int = 120):
        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        self.frame = Frame(parent, corner_radius=8) if USE_CTK else Frame(parent)
        Label(self.frame, text=title, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=8, pady=(8, 4))
        if USE_CTK:
            self.text = ctk.CTkTextbox(self.frame, height=height, font=("Consolas", 11))
        else:
            from tkinter import scrolledtext
            self.text = scrolledtext.ScrolledText(self.frame, height=max(5, height // 20), font=("Consolas", 11))
        self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def set(self, text: str):
        self.text.delete("1.0", "end")
        self.text.insert("end", text)


class AppWindow(ctk.CTk if USE_CTK else ctk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JuprisX Web-to-Android Builder")
        self.geometry("1280x820")
        self.minsize(900, 600)
        icon = _ROOT / "logo.ico"
        if icon.exists():
            try: self.iconbitmap(str(icon))
            except Exception: pass

        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        Button = ctk.CTkButton if USE_CTK else ctk.Button

        header = Frame(self, height=48, corner_radius=0) if USE_CTK else Frame(self, height=48)
        header.pack(fill="x"); header.pack_propagate(False)
        Label(header, text="JuprisX  · Web-to-Android", font=("Segoe UI", 18, "bold")).pack(side="left", padx=16, pady=10)
        self.status_lbl = Label(header, text="● Idle", font=("Segoe UI", 12)); self.status_lbl.pack(side="right", padx=12)
        Button(header, text="Play Store Assets", width=140, command=self.open_assets_window).pack(side="right", padx=6)
        Button(header, text="Check Android", width=120, command=self.setup_environment).pack(side="right", padx=6)
        Button(header, text="Auto-fix", width=90, command=lambda: self._with_project(self.auto_fix_project)).pack(side="right", padx=6)

        body = Frame(self); body.pack(fill="both", expand=True, padx=6, pady=6)
        left = Frame(body); left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        right = Frame(body); right.pack(side="right", fill="both", expand=True, padx=(4, 0))

        self.pm = ProjectManager(str(_ROOT / "workspace"))
        self.current_project = None
        self.project_table = ProjectTable(
            left, on_action=self.handle_project_action, on_new=self.new_project,
            on_select=self.select_project, on_delete=self.remove_project,
            on_clear_cache=self.clear_build_cache,
        )
        self.project_table.frame.pack(fill="x", padx=0, pady=(0, 4))

        mid = Frame(left); mid.pack(fill="both", expand=True)
        self.findings_panel = TextPanel(mid, "Web Findings", 130); self.findings_panel.frame.pack(fill="both", expand=True, pady=2)
        self.diff_panel = TextPanel(mid, "Patch Diff", 100); self.diff_panel.frame.pack(fill="both", expand=True, pady=2)
        self.reviewer_panel = ReviewerPanel(
            mid, on_approve=self.approve_edits,
            on_reject=lambda: self.log("Patch rejected."), on_rollback=self.rollback_project,
            on_diff=self.diff_panel.set,
            working_dir_getter=lambda: (self.current_project or {}).get("working_dir"),
        )
        self.reviewer_panel.frame.pack(fill="x", pady=2)

        services = ChatServices(
            scan=lambda: self._with_project(self.scan_project),
            build=lambda: self._with_project(self.build_project),
            keystore=lambda: self._with_project(self.generate_keystore),
            stage_edits=self.stage_edits_from_chat,
            create_project=self.create_project_from_chat,
            attach_folder=self.attach_folder_from_chat,
            default_projects_dir=self.default_projects_dir,
            open_assets=self.open_assets_window,
            setup_env=self.setup_environment,
            auto_fix=lambda: self._with_project(self.auto_fix_project),
        )
        self.chat_tab = ChatTab(right, context=ContextManager(), services=services)
        self.chat_tab.frame.pack(fill="both", expand=True)

        self.log_panel = TextPanel(self, "Log", 90); self.log_panel.frame.pack(fill="x", padx=6, pady=(0, 6))
        self._assets_win = None; self._assets_panel = None
        self.refresh_projects()

    def log(self, msg: str):
        self.log_panel.text.insert("end", f"> {msg}\n"); self.log_panel.text.see("end")

    def _notify(self, msg: str):
        self.log(msg)
        if getattr(self, "chat_tab", None): self.chat_tab.receive_message(msg)

    def set_status(self, text: str): self.status_lbl.configure(text=text)

    def _run_bg(self, work, done):
        def target():
            try: result, error = work(), None
            except Exception as exc: result, error = None, exc
            self.after(0, lambda: done(result, error))
        threading.Thread(target=target, daemon=True).start()

    def refresh_projects(self):
        projects = self.pm.list_projects(); self.project_table.load_projects(projects); self.log(f"Loaded {len(projects)} project(s).")

    def new_project(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Select HTML/JS project folder")
        if folder: self.select_project(self.pm.import_project(folder))

    def remove_project(self, project: dict):
        self.pm.delete_project(project["project_id"])
        if self.current_project and self.current_project.get("project_id") == project.get("project_id"): self.current_project = None
        self.refresh_projects()

    def select_project(self, project: dict):
        self.current_project = project
        findings = project.get("findings", [])
        self.findings_panel.set("\n".join(f"[{f.get('severity','INFO')}] {f.get('file','')}:{f.get('line',0)} {f.get('message','')}" for f in findings) or "No findings. Run scan.")
        self.reviewer_panel.show_findings(findings); self.reviewer_panel.show_validation(project.get("validation", {}))
        if getattr(self, "chat_tab", None): self.chat_tab.set_project(project)
        if self._assets_panel:
            try: self._assets_panel.refresh()
            except Exception: pass
        self.project_table.update_project(project)

    def _show_project(self, project: dict): self.select_project(project)

    def handle_project_action(self, project: dict, action: str):
        self.current_project = project
        if action == "scan": self.scan_project(project)
        elif action == "review": self.select_project(project)
        elif action == "build": self.build_project(project)

    def scan_project(self, project: dict):
        self.set_status("● Scanning"); self.log(f"Scanning {project['name']}...")
        self._run_bg(lambda: self.pm.scan(project), self._scan_done)

    def _scan_done(self, result, error):
        self.set_status("● Idle")
        if error: self.log(f"Scan failed: {error}"); return
        self._show_project(result); self.log(f"Scan done: {len(result.get('findings', []))} finding(s).")

    def approve_edits(self, edits: list):
        if not self.current_project: return
        try: self.pm.apply_edits(self.current_project, edits)
        except Exception as exc: self.log(f"Apply failed: {exc}"); return
        self.scan_project(self.current_project)

    def rollback_project(self):
        if self.current_project:
            self.pm.rollback(self.current_project); self.scan_project(self.current_project)

    def build_project(self, project: dict):
        try: self.pm.start_build(project)
        except (InvalidTransition, ValueError) as exc: self.log(f"Cannot build: {exc}"); return
        self.set_status("● Building"); self.log(f"Building {project['name']} -> APK + AAB...")
        def work():
            from part1_builder.compiler import CompilerPipeline
            return CompilerPipeline(project["working_dir"], self.pm.get_keystore(project), log=self.log).run_compile("both")
        def done(result, error):
            self.set_status("● Idle")
            if error: result = {"status": "error", "message": str(error)}
            self.pm.record_build(project, result); self._show_project(project)
            self.log(f"Build {result.get('status')}: {result.get('message','')}")
        self._run_bg(work, done)

    def clear_build_cache(self):
        self.log("Gradle/build cache is project-local; use Clean in the generated android project before a full rebuild.")

    def setup_environment(self):
        self.set_status("● Checking Android"); self._notify("Checking JDK / Gradle / Android SDK...")
        def work():
            from part1_builder.wsl_checker import check_wsl_environment
            return check_wsl_environment()
        def done(env, error):
            self.set_status("● Idle")
            if error: self._notify(f"Toolchain check failed: {error}"); return
            if env.get("ready"): self._notify("Android build environment ready.")
            else: self._notify("; ".join(env.get("errors", []) or ["Android toolchain incomplete."]))
        self._run_bg(work, done)

    def auto_fix_project(self, project: dict):
        self.set_status("● Auto-fixing")
        provider = self.chat_tab.engine.make_fix_provider()
        self._run_bg(lambda: self.pm.agentic_fix(project, provider, 3, log=self.log), self._auto_fix_done)

    def _auto_fix_done(self, result, error):
        self.set_status("● Idle")
        if error: self.log(f"Auto-fix failed: {error}"); return
        self._show_project(result); self._notify(f"Auto-fix complete: {len(result.get('findings', []))} finding(s) remain.")

    def _with_project(self, fn):
        if self.current_project: fn(self.current_project)
        else: self._notify("No active project.")

    def default_projects_dir(self):
        p = _ROOT / "workspace" / "projects"; p.mkdir(parents=True, exist_ok=True); return str(p)

    def create_project_from_chat(self, name: str, folder: str, files: dict):
        project = self.pm.create_project_with_files(name, folder, files); self._show_project(project); return project

    def attach_folder_from_chat(self, folder: str):
        project = self.pm.import_project(folder); self._show_project(project); return project

    def stage_edits_from_chat(self, edits: list):
        if self.current_project: self.reviewer_panel.stage_edits(edits)
        else: self._notify("Select a project before accepting a patch.")

    def generate_keystore(self, project: dict):
        from core_engine.keystore_manager import KeystoreManager
        if project.get("keystore", {}).get("path"): self._notify("Project already has a keystore; reusing it."); return
        self.set_status("● Keystore")
        def work(): return KeystoreManager(project["working_dir"]).ensure()
        def done(info, error):
            self.set_status("● Idle")
            if error: self._notify(f"Keystore failed: {error}"); return
            self.pm.save_keystore(project, info); self._show_project(project); self._notify(f"Keystore ready: {info['path']}")
        self._run_bg(work, done)

    def open_assets_window(self):
        if not self.current_project: self._notify("Select a project first."); return
        from part5_assets.assets_panel import AssetsPanel
        Top = ctk.CTkToplevel if USE_CTK else ctk.Toplevel
        if self._assets_win:
            try:
                if self._assets_win.winfo_exists(): self._assets_win.lift(); self._assets_panel.refresh(); return
            except Exception: pass
        self._assets_win = Top(self); self._assets_win.title("Play Store Assets"); self._assets_win.geometry("760x640")
        self._assets_panel = AssetsPanel(self._assets_win, project_getter=lambda: self.current_project, on_saved=self._asset_saved, on_log=self.log)
        self._assets_panel.frame.pack(fill="both", expand=True, padx=6, pady=6)

    def _asset_saved(self, kind: str, path: str):
        if self.current_project: self.pm.record_asset(self.current_project, kind, path)

    def run(self): self.mainloop()
