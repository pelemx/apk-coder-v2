"""
Project Table GUI - list of projects with status and actions.
"""
from __future__ import annotations

from datetime import datetime

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    import tkinter as ctk
    USE_CTK = False

STATUS_COLORS = {
    "new": "#9aa0a6", "scanning": "#4dabf7", "needs_fix": "#ff6b6b",
    "plan_ready": "#fcc419", "fixed": "#fcc419", "validated": "#69db7c",
    "ready_to_build": "#51cf66", "building": "#4dabf7",
    "playstore_ready": "#20c997", "missing": "#868e96",
}

ACTIONS = {
    "new": ("Scan", "scan"),
    "scanning": ("Scanning...", None),
    "needs_fix": ("Scan", "scan"),
    "plan_ready": ("Review", "review"),
    "fixed": ("Review", "review"),
    "validated": ("Scan", "scan"),
    "ready_to_build": ("Build", "build"),
    "building": ("Building...", None),
    "playstore_ready": ("Review", "review"),
    "missing": ("—", None),
}

def _w(chars: int) -> int:
    return chars * 9 if USE_CTK else chars

def format_last_scan(value) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%d %b")

def action_for(project: dict) -> tuple[str, str | None]:
    return ACTIONS.get(project.get("status", "new"), ("Review", "review"))

class ProjectTable:
    # TAMBAHKAN on_clear_cache=None di sini
    def __init__(self, parent_widget, on_action=None, on_new=None,
                 on_select=None, on_delete=None, on_clear_cache=None):
        self.parent_widget = parent_widget
        self.projects: list[dict] = []
        self.selected_id: str | None = None
        self.on_action = on_action
        self.on_new = on_new
        self.on_select = on_select
        self.on_delete = on_delete
        self.on_clear_cache = on_clear_cache  # Simpan callback
        self._row_widgets: list = []

        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        Button = ctk.CTkButton if USE_CTK else ctk.Button

        self.frame = Frame(parent_widget, corner_radius=8) if USE_CTK else Frame(parent_widget)
        Label(self.frame, text="Project Table", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=10, pady=(10, 4))

        header = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        header.pack(fill="x", padx=8, pady=(0, 2))
        for col, w in [("ID", 8), ("Nama Project", 22), ("Status", 16), ("Last Scan", 10), ("Action", 14)]:
            Label(header, text=col, font=("Segoe UI", 11, "bold"), width=_w(w), anchor="w").pack(
                side="left", padx=2)

        self.rows_frame = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        self.rows_frame.pack(fill="x", padx=8, pady=(0, 6))

        bar = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        bar.pack(fill="x", padx=8, pady=(0, 10))
        Button(bar, text="Refresh", width=90, command=self.render).pack(side="left", padx=2)
        Button(bar, text="New Project", width=110, command=self._on_new).pack(side="left", padx=2)
        Button(bar, text="Remove", width=90, command=self._on_delete).pack(side="left", padx=2)
        
        # TOMBOL CLEAR CACHE DIPINDAHKAN KE SINI (SEBELAH REMOVE)
        if self.on_clear_cache:
            Button(bar, text="Clear WSL Cache", width=130, 
                   fg_color="#C62828", hover_color="#b71c1c",
                   command=self.on_clear_cache).pack(side="left", padx=2)

    # ---- data -----------------------------------------------------------
    def load_projects(self, project_list: list):
        self.projects = list(project_list or [])
        ids = {self._pid(p) for p in self.projects}
        if self.selected_id not in ids:
            self.selected_id = None
        self.render()

    def update_project(self, project: dict):
        pid = self._pid(project)
        for i, p in enumerate(self.projects):
            if self._pid(p) == pid:
                self.projects[i] = project
                break
        else:
            self.projects.append(project)
        self.render()

    def get_selected(self) -> dict | None:
        for p in self.projects:
            if self._pid(p) == self.selected_id:
                return p
        return None

    @staticmethod
    def _pid(p: dict) -> str:
        return str(p.get("project_id", p.get("id", "")))

    # ---- rendering ------------------------------------------------------
    def render(self):
        for w in self._row_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._row_widgets.clear()

        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        Button = ctk.CTkButton if USE_CTK else ctk.Button

        if not self.projects:
            empty = Label(self.rows_frame, text="(no projects)", anchor="w")
            empty.pack(fill="x", pady=4)
            self._row_widgets.append(empty)
            return

        for p in self.projects:
            pid = self._pid(p)
            selected = pid == self.selected_id
            if USE_CTK:
                row = Frame(self.rows_frame, fg_color=("gray80", "gray25") if selected else "transparent")
            else:
                row = Frame(self.rows_frame, bg="#cce5ff" if selected else None)
            row.pack(fill="x", pady=2)

            status = p.get("status", "new")
            labels = [
                (pid[:8], 8, None),
                (p.get("name", "—"), 22, None),
                (status, 16, STATUS_COLORS.get(status)),
                (format_last_scan(p.get("last_scan")), 10, None),
            ]
            for text, w, color in labels:
                kw = {"text_color": color} if (color and USE_CTK) else ({"fg": color} if color else {})
                lbl = Label(row, text=text, width=_w(w), anchor="w", **kw)
                lbl.pack(side="left", padx=2)
                lbl.bind("<Button-1>", lambda _e, proj=p: self._select(proj))

            text, action = action_for(p)
            btn = Button(row, text=text, width=100,
                         command=(lambda proj=p, a=action: self._fire(proj, a)) if action else None)
            if not action:
                try:
                    btn.configure(state="disabled")
                except Exception:
                    pass
            btn.pack(side="left", padx=4)
            row.bind("<Button-1>", lambda _e, proj=p: self._select(proj))
            self._row_widgets.append(row)

    # ---- events ---------------------------------------------------------
    def _select(self, project: dict):
        self.selected_id = self._pid(project)
        self.render()
        if self.on_select:
            self.on_select(project)

    def _fire(self, project: dict, action: str):
        self.selected_id = self._pid(project)
        if self.on_action:
            self.on_action(project, action)
        else:
            print(f"[ProjectTable] {action}: {project.get('name')} ({project.get('status')})")

    def _on_new(self):
        if self.on_new:
            self.on_new()

    def _on_delete(self):
        proj = self.get_selected()
        if proj and self.on_delete:
            self.on_delete(proj)