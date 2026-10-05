"""
JuprisX Pygame Agentic Desktop - Main GUI
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    USE_CTK = True
except ImportError:
    import tkinter as ctk
    USE_CTK = False

import threading
from pathlib import Path

from part3_project.project_manager import ProjectManager
from part3_project.project_table import ProjectTable
from part3_project.reviewer import ReviewerPanel
from part3_project.workflow import InvalidTransition
from part4_chat.chat_tab import ChatServices, ChatTab
from part4_chat.context_manager import ContextManager


class FindingsPanel:
    def __init__(self, parent):
        self.parent = parent
        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label

        self.frame = Frame(parent, corner_radius=8) if USE_CTK else Frame(parent)
        self.frame.pack(fill="both", expand=True, padx=4, pady=4)

        Label(self.frame, text="Findings", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )

        if USE_CTK:
            self.text = ctk.CTkTextbox(self.frame, height=120, font=("Consolas", 11))
            self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        else:
            from tkinter import scrolledtext
            self.text = scrolledtext.ScrolledText(self.frame, height=6, font=("Consolas", 11))
            self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.set_findings([])

    def set_findings(self, findings: list):
        self.text.delete("1.0", "end")
        if not findings:
            self.text.insert("end", "No findings yet. Run scan first.\n")
            return
        for f in findings:
            sev = f.get("severity", "LOW").upper() if isinstance(f, dict) else "INFO"
            msg = f.get("message", str(f)) if isinstance(f, dict) else str(f)
            loc = ""
            if isinstance(f, dict) and f.get("file"):
                loc = f"{f['file']}:{f.get('line', 0)}  "
            self.text.insert("end", f"[{sev}] {loc}{msg}\n")


class DiffPanel:
    def __init__(self, parent):
        self.parent = parent
        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label

        self.frame = Frame(parent, corner_radius=8) if USE_CTK else Frame(parent)
        self.frame.pack(fill="both", expand=True, padx=4, pady=4)

        Label(self.frame, text="Diff (Original -> Fixed)", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )

        if USE_CTK:
            self.text = ctk.CTkTextbox(self.frame, height=120, font=("Consolas", 11))
            self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        else:
            from tkinter import scrolledtext
            self.text = scrolledtext.ScrolledText(self.frame, height=6, font=("Consolas", 11))
            self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.show_diff("", "")

    def show_unified(self, diff_text: str):
        self.text.delete("1.0", "end")
        self.text.insert("end", diff_text or "No patch applied yet.\n")

    def show_diff(self, original: str, fixed: str):
        self.text.delete("1.0", "end")
        if not original and not fixed:
            self.text.insert("end", "No patch applied yet.\n")
            return
        self.text.insert("end", "--- original\n+++ fixed\n\n")
        if original:
            for line in original.splitlines():
                self.text.insert("end", f"- {line}\n")
        if fixed:
            for line in fixed.splitlines():
                self.text.insert("end", f"+ {line}\n")


class LogPanel:
    def __init__(self, parent):
        self.parent = parent
        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label

        self.frame = Frame(parent, corner_radius=8) if USE_CTK else Frame(parent)
        self.frame.pack(fill="x", padx=4, pady=4)

        Label(self.frame, text="Log", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )

        if USE_CTK:
            self.text = ctk.CTkTextbox(self.frame, height=200, font=("Consolas", 11))
            self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        else:
            from tkinter import scrolledtext
            self.text = scrolledtext.ScrolledText(self.frame, height=12, font=("Consolas", 11))
            self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.log("JuprisX ready.")

    def log(self, msg: str):
        self.text.insert("end", f"> {msg}\n")
        self.text.see("end")


class AppWindow(ctk.CTk if USE_CTK else ctk.Tk):
    def __init__(self):
        super().__init__()
        icon_path = os.path.join(_ROOT, "logo.ico")
        if os.path.isfile(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception as exc:
                print(f"[WARN] Failed to load window icon: {exc}")

        self.title("Juprisx-APK-Builder-.V.0.2")
        self.geometry("1280x820")
        self.minsize(900, 600)

        Header = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label

        # Header bar
        header = Header(self, height=48, corner_radius=0) if USE_CTK else Header(self, height=48)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        Label(
            header,
            text="JuprisX  · APK-Coder-X2",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left", padx=16, pady=10)

        self.status_lbl = Label(header, text="● Idle", font=("Segoe UI", 12))
        self.status_lbl.pack(side="right", padx=16)
        Button = ctk.CTkButton if USE_CTK else ctk.Button
        Button(header, text="Play Store Assets", width=140,
               command=self.open_assets_window).pack(side="right", padx=8)
        Button(header, text="Setup WSL", width=100,
               command=lambda: self.setup_environment()).pack(side="right", padx=4)
        Button(header, text="Auto-fix (AI)", width=110,
               command=lambda: self._with_project(self.auto_fix_project)).pack(side="right", padx=4)
        self._assets_win = None
        self._assets_panel = None

        # Body
        body = Header(self) if USE_CTK else Header(self)
        body.pack(fill="both", expand=True, padx=6, pady=6)

        # Left column
        left = Header(body) if USE_CTK else Header(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))

        workspace = Path(_ROOT) / "workspace"
        self.pm = ProjectManager(str(workspace))
        self.current_project = None

        # Inisialisasi ProjectTable dengan callback on_clear_cache
        self.project_table = ProjectTable(
            left,
            on_action=self.handle_project_action,
            on_new=self.new_project,
            on_select=self.select_project,
            on_delete=self.remove_project,
            on_clear_cache=self.clear_wsl_cache, 
        )
        self.project_table.frame.pack(fill="x", padx=0, pady=(0, 4))
        
        # TOMBOL CLEAR CACHE YANG LAMA DI HAPUS DARI SINI

        mid = Header(left) if USE_CTK else Header(left)
        mid.pack(fill="both", expand=True)

        self.findings_panel = FindingsPanel(mid)
        self.diff_panel = DiffPanel(mid)

        self.reviewer_panel = ReviewerPanel(
            mid,
            on_approve=self.approve_edits,
            on_reject=lambda: self.log_panel.log("Patch rejected."),
            on_rollback=self.rollback_project,
            on_diff=self.diff_panel.show_unified,
            working_dir_getter=lambda: (self.current_project or {}).get("working_dir"),
        )
        self.reviewer_panel.frame.pack(fill="x", padx=0, pady=(0, 4), before=self.findings_panel.frame)

        # Right column - Chat
        right = Header(body) if USE_CTK else Header(body)
        right.pack(side="right", fill="both", expand=True, padx=(4, 0))

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

        # Bottom log
        self.log_panel = LogPanel(self)

        self.refresh_projects()

    def clear_wsl_cache(self):
        if not self.current_project:
            self._notify("Pilih project dulu dari tabel untuk menghapus cache.")
            return
        self.set_status("● Clearing Cache")
        self.log_panel.log(f"Menghapus cache Buildozer untuk project {self.current_project['name']}...")
        
        def work():
            import re
            from pathlib import Path
            from part1_builder.wsl_checker import run_in_wsl
            dir_name = Path(self.current_project["working_dir"]).name
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dir_name) or "project"
            cmd = f"rm -rf ~/.juprisx/build/{slug}/.buildozer"
            return run_in_wsl(cmd, timeout=60)
            
        def done(result, error):
            self.set_status("● Idle")
            if error:
                self._notify(f"Gagal hapus cache: {error}")
            elif result.returncode != 0:
                self._notify(f"Gagal hapus cache: {result.stderr}")
            else:
                self._notify("Cache Buildozer (WSL) berhasil dihapus secara bersih! Silakan klik Build lagi.")
                
        self._run_bg(work, done)

    # ---- project handling (Part 3) ------------------------------------
    def refresh_projects(self):
        projects = self.pm.list_projects()
        self.project_table.load_projects(projects)
        self.log_panel.log(f"Loaded {len(projects)} project(s).")

    def new_project(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Select Pygame project folder")
        if not folder:
            return
        proj = self.pm.import_project(folder)
        self.project_table.update_project(proj)
        self.select_project(proj)
        self.log_panel.log(f"Added project: {proj['name']}")

    def remove_project(self, project: dict):
        self.pm.delete_project(project["project_id"])
        if self.current_project and self.current_project["project_id"] == project["project_id"]:
            self.current_project = None
        self.refresh_projects()

    def select_project(self, project: dict):
        self.current_project = project
        self.findings_panel.set_findings(project.get("findings", []))
        self.reviewer_panel.show_findings(project.get("findings", []))
        self.reviewer_panel.show_validation(project.get("validation", {}))
        if getattr(self, "chat_tab", None):
            self.chat_tab.set_project(project)
        panel = getattr(self, "_assets_panel", None)
        if panel is not None:
            try:
                panel.refresh()
            except Exception:
                pass

    def _show_project(self, project: dict):
        self.current_project = project
        self.project_table.update_project(project)
        self.select_project(project)

    def handle_project_action(self, project: dict, action: str):
        self.current_project = project
        if action == "scan":
            self.scan_project(project)
        elif action == "review":
            self.select_project(project)
            self.log_panel.log(f"Reviewing {project['name']} ({project['status']}).")
        elif action == "build":
            self.build_project(project)

    def _run_bg(self, work, done):
        """Run work() off the UI thread, then done(result, error) on it."""
        def target():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, exc
            self.after(0, lambda: done(result, error))
        threading.Thread(target=target, daemon=True).start()

    def scan_project(self, project: dict):
        self.set_status("● Scanning")
        self.log_panel.log(f"Scanning {project['name']}...")

        def done(result, error):
            self.set_status("● Idle")
            if error:
                self.log_panel.log(f"Scan failed: {error}")
                return
            self._show_project(result)
            self.log_panel.log(
                f"Scan done: {len(result['findings'])} finding(s), status={result['status']}")

        self._run_bg(lambda: self.pm.scan(project), done)

    def approve_edits(self, edits: list):
        project = self.current_project
        if not project:
            return
        try:
            self.pm.apply_edits(project, edits)
        except Exception as exc:
            self.log_panel.log(f"Apply failed: {exc}")
            return
        self.log_panel.log(f"Applied {len(edits)} edit(s) with backup. Re-scanning...")
        self.scan_project(project)

    def rollback_project(self):
        project = self.current_project
        if not project:
            return
        results = self.pm.rollback(project)
        restored = sum(1 for r in results if r.get("status") == "rolled_back")
        self.log_panel.log(f"Rollback: {restored} file(s) restored.")
        self._show_project(project)

    def build_project(self, project: dict):
        try:
            self.pm.start_build(project)
        except (InvalidTransition, ValueError) as exc:
            self.log_panel.log(f"Cannot build: {exc}")
            return
        
        self.project_table.update_project(project)
        self.set_status("● Building")
        self.log_panel.log(f"Building {project['name']}...")

        def work():
            import re
            from pathlib import Path
            from part1_builder.wsl_checker import run_in_wsl
            
            # 1. OTOMATIS HAPUS CACHE PYGAME LAMA VIA WSL
            dir_name = Path(project["working_dir"]).name
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dir_name) or "project"
            clean_cmd = f"rm -rf ~/.juprisx/build/{slug}/.buildozer/android/platform/build-*/build/other_builds/pygame*"
            
            try:
                run_in_wsl(clean_cmd, timeout=30)
                self.after(0, lambda: self.log_panel.log("[Auto-Clean] Cache pygame lama berhasil dibersihkan."))
            except Exception as e:
                self.after(0, lambda: self.log_panel.log(f"[Auto-Clean] Info: Gagal hapus cache ({e}), melanjutkan build..."))

            # 2. LANJUTKAN BUILD NORMAL
            from part1_builder.compiler import CompilerPipeline
            return CompilerPipeline(project["working_dir"], self.pm.get_keystore(project),
                                    log=self._bg_log).run_compile()

        def done(result, error):
            self.set_status("● Idle")
            if error:
                result = {"status": "error", "message": str(error)}
            self.pm.record_build(project, result)
            self._show_project(project)
            self.log_panel.log(f"Build {result['status']}: {result.get('message', '')}")

        self._run_bg(work, done)

    def _bg_log(self, line: str):
        """Thread-safe logging for background workers."""
        self.after(0, lambda: self.log_panel.log(line))

    def setup_environment(self):
        """Self-heal the WSL build environment (apt packages + Buildozer venv)."""
        self.set_status("● Setting up WSL")
        self._notify("Menyiapkan WSL build environment...")

        def work():
            from part1_builder.wsl_checker import apply_setup
            return apply_setup(log=self._bg_log)

        def done(env, error):
            self.set_status("● Idle")
            if error:
                self._notify(f"Setup gagal: {error}")
                return
            if env.get("ready"):
                self._notify("Build environment siap (WSL, JDK, Buildozer).")
            else:
                self._notify("Environment belum lengkap: " + "; ".join(env.get("errors", []) or ["lihat Log"]))
                for step in env.get("setup_log", []):
                    if step["returncode"] != 0:
                        self._bg_log(f"[setup] {step['step']} gagal: {step['tail'][-300:]}")

        self._run_bg(work, done)

    def auto_fix_project(self, project: dict):
        provider = self.chat_tab.engine.make_fix_provider()
        self.set_status("● Auto-fixing")
        self.log_panel.log(f"Auto-fix {project['name']} (maks 3 percobaan)...")

        def done(result, error):
            self.set_status("● Idle")
            if error:
                self.log_panel.log(f"Auto-fix gagal: {error}")
                return
            self._show_project(result)
            notes = "; ".join(a.get("note") or "patched" for a in result.get("agent_attempts", []))
            self._notify(f"Auto-fix selesai: status={result['status']}, "
                         f"{len(result['findings'])} finding tersisa. ({notes})")

        self._run_bg(lambda: self.pm.agentic_fix(project, provider, 3, log=self._bg_log), done)

    # ---- chat services (Part 4) ----------------------------------------
    def _notify(self, msg: str):
        self.log_panel.log(msg)
        if getattr(self, "chat_tab", None):
            self.chat_tab.receive_message(msg)

    def _with_project(self, fn):
        if self.current_project:
            fn(self.current_project)
        else:
            self._notify("Tidak ada project aktif.")

    def default_projects_dir(self) -> str:
        path = Path(_ROOT) / "workspace" / "projects"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def create_project_from_chat(self, name: str, folder: str, files: dict) -> dict:
        proj = self.pm.create_project_with_files(name, folder, files)
        self._show_project(proj)
        self.log_panel.log(f"Project dibuat dari chat: {name} -> {folder}")
        return proj

    def attach_folder_from_chat(self, folder: str) -> dict:
        proj = self.pm.import_project(folder)
        self._show_project(proj)
        return proj

    def stage_edits_from_chat(self, edits: list):
        if not self.current_project:
            self._notify("Pilih project dulu sebelum menerima patch.")
            return
        self.reviewer_panel.stage_edits(edits)
        self.log_panel.log(f"{len(edits)} patch menunggu review (Approve / Reject).")

    def generate_keystore(self, project: dict):
        from tkinter import simpledialog
        if project.get("keystore", {}).get("path"):
            self._notify("Project ini sudah punya keystore. Tidak ditimpa agar tidak hilang.")
            return
        alias = simpledialog.askstring("Keystore", "Alias:", initialvalue="juprisx-release", parent=self)
        if not alias:
            return
        pw = simpledialog.askstring("Keystore", "Password (min 6 karakter):", show="*", parent=self)
        if not pw or len(pw) < 6:
            self._notify("Keystore dibatalkan: password minimal 6 karakter.")
            return
        rel = "release.jks"
        target = Path(project["working_dir"]) / rel
        if target.exists():
            self._notify(f"{rel} sudah ada di folder project; tidak ditimpa.")
            return
        self.set_status("● Keystore")

        def work():
            from part1_builder.keystore import generate_keystore
            return generate_keystore(str(target), alias, pw, pw)

        def done(result, error):
            self.set_status("● Idle")
            if error:
                self._notify(f"Keystore gagal: {error}")
                return
            self.pm.set_keystore(project, rel, alias, pw, pw, result.get("generated_at"))
            self._show_project(project)
            self._notify(f"Keystore dibuat: {target}. BACKUP file ini dan passwordnya - "
                         "tanpa keystore yang sama kamu tidak bisa update app di Play Store.")

        self._run_bg(work, done)

    # ---- Play Store assets (Part 5) -------------------------------------
    def open_assets_window(self):
        if not self.current_project:
            self._notify("Pilih project dulu sebelum membuat asset Play Store.")
            return
        from part5_assets.assets_panel import AssetsPanel
        win = self._assets_win
        if win is not None:
            try:
                if win.winfo_exists():
                    self._assets_panel.refresh()
                    win.deiconify()
                    win.lift()
                    return
            except Exception:
                pass
        Top = ctk.CTkToplevel if USE_CTK else ctk.Toplevel
        win = Top(self)
        win.title("Play Store Assets")
        win.geometry("760x640")
        self._assets_win = win
        self._assets_panel = AssetsPanel(
            win,
            project_getter=lambda: self.current_project,
            on_saved=self._asset_saved,
            on_log=self.log_panel.log,
        )
        self._assets_panel.frame.pack(fill="both", expand=True, padx=6, pady=6)

    def _asset_saved(self, kind: str, path: str):
        if self.current_project:
            self.pm.record_asset(self.current_project, kind, path)

    def set_status(self, text: str):
        self.status_lbl.configure(text=text)

    def run(self):
        self.mainloop()
