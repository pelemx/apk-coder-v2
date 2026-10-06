from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .analyzer import Analyzer
from .planner import Planner
from .fixer import Fixer
from .validator import Validator
from .prompts import build_fix_prompt

FixProvider = Callable[[str], "dict[str, str]"]


class AgentClient:
    """Local controller for inspection/validation/patching; MCP remains the AI backbone."""

    def __init__(self, working_dir: str, builder_contract=None, mcp_client=None,
                 fix_provider: FixProvider | None = None, log=None):
        self.working_dir = str(Path(working_dir).expanduser().resolve())
        self.builder_contract = builder_contract or Analyzer.default_builder_contract()
        self.mcp_client = mcp_client
        self.fix_provider = fix_provider
        self.log = log or (lambda line: None)
        self.state = {"status": "new", "working_dir": self.working_dir, "findings": [], "plan": [], "patches": [], "validation": {}, "scan": {}}

    def run_agentic_loop(self, apply_fixes=False, max_attempts=3, auto_setup=False, approve=None):
        self.state["attempts"] = []
        previous_signature = None
        for attempt in range(1, max_attempts + 1):
            self.log(f"[agent] attempt {attempt}/{max_attempts}: scan")
            self.scan(); self.understand(); self.check_builder_constraint(); self.check_dependencies()
            self.find_problems(); self.build_fix_plan(); self.validate()
            signature = frozenset((f["code"], f["file"], f["line"]) for f in self.state["findings"])
            entry = {"attempt": attempt, "findings": len(self.state["findings"]), "validation": dict(self.state["validation"]), "patched": [], "note": ""}
            self.state["attempts"].append(entry)
            if self.is_ready(): entry["note"] = "ready"; break
            if not apply_fixes or self.fix_provider is None:
                entry["note"] = "fixes not requested" if not apply_fixes else "no fix provider (MCP offline)"; break
            if previous_signature is not None and signature == previous_signature:
                entry["note"] = "no progress after last patch, stopping"; break
            previous_signature = signature
            edits = self.request_edits(attempt)
            if not edits: entry["note"] = "provider returned no usable edits"; break
            if approve is not None and not approve(edits, attempt): entry["note"] = "edits rejected by reviewer"; break
            patches = self.apply_patch(edits); entry["patched"] = [p["file"] for p in patches]
        self.rescan(); self.write_report(); return self.final_result()

    def is_ready(self):
        return not self.state["findings"] and bool(self.state["validation"].get("passed"))

    def request_edits(self, attempt):
        validator = Validator(self.working_dir)
        prompt = build_fix_prompt(self.state["findings"], validator.unresolved_imports(), self.state["validation"], attempt)
        try: files = self.fix_provider(prompt) or {}
        except Exception as exc:
            self.log(f"[agent] fix provider failed: {exc}"); return []
        return [{"file": rel, "content": content} for rel, content in files.items() if isinstance(content, str) and content.strip()]

    def write_report(self):
        reports = Path(self.working_dir) / ".juprisx" / "reports"; reports.mkdir(parents=True, exist_ok=True)
        path = reports / f"report-{datetime.now():%Y%m%d-%H%M%S}.json"
        data = {k: self.state.get(k) for k in ("status", "attempts", "findings", "remaining_findings", "plan", "patches", "validation")}
        data["created_at"] = datetime.now().isoformat(timespec="seconds")
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self.state["report"] = str(path); return str(path)

    def scan(self):
        self.state["status"] = "scanning"; self.state["scan"] = Analyzer(self.working_dir, self.builder_contract).analyze(); return self.state["scan"]

    def understand(self):
        self.state["status"] = "understanding"; self.state["understanding"] = {"project_root": self.working_dir, "builder": self.builder_contract.get("name"), "immutable_builder": True}; return self.state["understanding"]

    def check_builder_constraint(self):
        self.state["builder_check"] = {"immutable": True, "rules": self.builder_contract.get("rules", [])}; return self.state["builder_check"]

    def check_wsl(self):
        self.state["wsl_check"] = {"ready": True, "mode": "native-gradle"}; return self.state["wsl_check"]

    def check_dependencies(self):
        self.state["dependency_check"] = Validator(self.working_dir).validate_dependencies(); return self.state["dependency_check"]

    def find_problems(self):
        self.state["findings"] = self.state.get("scan", {}).get("findings", []); self.state["status"] = "needs_fix" if self.state["findings"] else "clean"; return self.state["findings"]

    def build_fix_plan(self):
        self.state["plan"] = Planner(self.state["findings"]).build_fix_plan();
        if self.state["plan"]: self.state["status"] = "plan_ready"
        return self.state["plan"]

    def apply_patch(self, edits=None):
        if not edits: self.state["patches"] = []; return []
        fixer = Fixer(self.working_dir); patches = [fixer.apply_file_replacement(e["file"], e["content"]) for e in edits]
        self.state["patches"] = patches; self.state.setdefault("all_patches", []).extend(patches); self.state["status"] = "fixed"; return patches

    def validate(self):
        self.state["validation"] = Validator(self.working_dir).validate_all();
        self.state["status"] = "validated" if self.state["validation"].get("passed") and not self.state.get("findings") else "needs_fix"; return self.state["validation"]

    def rescan(self):
        self.state["rescan"] = Analyzer(self.working_dir, self.builder_contract).analyze(); self.state["remaining_findings"] = self.state["rescan"].get("findings", [])
        self.state["status"] = "ready_to_build" if not self.state["remaining_findings"] and self.state["validation"].get("passed") else "needs_fix"; return self.state["rescan"]

    def final_result(self): return self.state
