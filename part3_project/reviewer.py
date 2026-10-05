"""
Reviewer Panel - findings summary, validation, diff, Approve / Reject / Rollback.

The panel never touches files itself. It stages proposed edits and calls back
into the app, which hands approved edits to ProjectManager (backup + validate).

Callbacks (all optional):
    on_approve(edits)   edits = [{'file': rel, 'content': new_text}]
    on_reject()
    on_rollback()
    on_diff(text)       unified diff text for the DiffPanel
"""
from __future__ import annotations

import difflib
from pathlib import Path

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    import tkinter as ctk
    USE_CTK = False


def unified_diff(original: str, fixed: str, filename: str = "file") -> str:
    """Real unified diff (only changed hunks), empty string if identical."""
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile=f"a/{filename}", tofile=f"b/{filename}", n=2,
    ))


def severity_counts(findings: list) -> dict[str, int]:
    counts = {"HIGH": 0, "MED": 0, "LOW": 0}
    for f in findings:
        sev = str(f.get("severity", "LOW")).upper() if isinstance(f, dict) else "LOW"
        counts[sev if sev in counts else "LOW"] += 1
    return counts


def validation_summary(validation: dict) -> tuple[int, int]:
    checks = {k: v for k, v in (validation or {}).items() if k != "passed"}
    return sum(1 for v in checks.values() if v), len(checks)


class ReviewerPanel:
    def __init__(self, parent_widget, on_approve=None, on_reject=None,
                 on_rollback=None, on_diff=None, working_dir_getter=None):
        self.parent_widget = parent_widget
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.on_rollback = on_rollback
        self.on_diff = on_diff
        self.working_dir_getter = working_dir_getter  # () -> str | None

        self.findings: list = []
        self.validation: dict = {}
        self.pending_edits: list[dict] = []

        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        Button = ctk.CTkButton if USE_CTK else ctk.Button

        self.frame = Frame(parent_widget, corner_radius=8) if USE_CTK else Frame(parent_widget)
        Label(self.frame, text="Reviewer", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=10, pady=(10, 4))

        self.summary_lbl = Label(self.frame, text="Validation: — | Findings: 0",
                                 anchor="w", font=("Segoe UI", 11))
        self.summary_lbl.pack(fill="x", padx=10, pady=2)
        self.pending_lbl = Label(self.frame, text="No pending patch", anchor="w",
                                 font=("Segoe UI", 11))
        self.pending_lbl.pack(fill="x", padx=10, pady=2)

        btn_row = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        btn_row.pack(fill="x", padx=8, pady=(4, 10))
        self.approve_btn = Button(btn_row, text="Approve", width=90, command=self._approve)
        self.reject_btn = Button(btn_row, text="Reject", width=90, command=self._reject)
        self.rollback_btn = Button(btn_row, text="Rollback", width=90, command=self._rollback)
        for b in (self.approve_btn, self.reject_btn, self.rollback_btn):
            b.pack(side="left", padx=3)
        self._update_buttons()

    # ---- inputs ---------------------------------------------------------
    def show_findings(self, findings: list):
        self.findings = findings or []
        self._refresh_summary()

    def show_validation(self, validation_result: dict):
        self.validation = validation_result or {}
        self._refresh_summary()

    def show_diff(self, original: str, fixed: str, filename: str = "file"):
        if self.on_diff:
            self.on_diff(unified_diff(original, fixed, filename))

    def stage_edits(self, edits: list[dict]):
        """Stage proposed edits [{'file','content'}] for review. Nothing is written yet."""
        self.pending_edits = [e for e in (edits or []) if e.get("file") is not None]
        wd = self.working_dir_getter() if self.working_dir_getter else None
        parts = []
        for e in self.pending_edits:
            old = ""
            if wd:
                target = Path(wd) / e["file"]
                if target.is_file():
                    try:
                        old = target.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        old = ""
            parts.append(unified_diff(old, e["content"], e["file"]) or f"(no change: {e['file']})\n")
        if self.on_diff:
            self.on_diff("\n".join(parts) if parts else "")
        self._refresh_summary()
        self._update_buttons()

    def render_buttons(self):
        self._update_buttons()

    # ---- state ----------------------------------------------------------
    def _refresh_summary(self):
        ok, total = validation_summary(self.validation)
        c = severity_counts(self.findings)
        val = f"{ok}/{total} passed" if total else "—"
        self.summary_lbl.configure(
            text=f"Validation: {val}  |  Findings: {len(self.findings)} "
                 f"(HIGH {c['HIGH']} / MED {c['MED']} / LOW {c['LOW']})")
        n = len(self.pending_edits)
        self.pending_lbl.configure(
            text=f"Pending patch: {n} file(s)" if n else "No pending patch")

    def _update_buttons(self):
        has = bool(self.pending_edits)
        for btn, enabled in ((self.approve_btn, has), (self.reject_btn, has),
                             (self.rollback_btn, True)):
            try:
                btn.configure(state="normal" if enabled else "disabled")
            except Exception:
                pass

    # ---- actions --------------------------------------------------------
    def _approve(self):
        if not self.pending_edits:
            return
        edits, self.pending_edits = self.pending_edits, []
        self._refresh_summary()
        self._update_buttons()
        if self.on_approve:
            self.on_approve(edits)

    def _reject(self):
        self.pending_edits = []
        if self.on_diff:
            self.on_diff("")
        self._refresh_summary()
        self._update_buttons()
        if self.on_reject:
            self.on_reject()

    def _rollback(self):
        self.pending_edits = []
        self._refresh_summary()
        self._update_buttons()
        if self.on_rollback:
            self.on_rollback()
