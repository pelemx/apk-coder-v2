from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .analyzer import Analyzer
from .planner import Planner
from .fixer import Fixer
from .validator import Validator
from .prompts import build_fix_prompt

# fix_provider(prompt) -> {relative_path: new_content}; supplied by the MCP/chat layer.
FixProvider = Callable[[str], "dict[str, str]"]


class AgentClient:
    """
    Orchestrates the local compatibility pipeline.

    The MCP server remains the AI/agentic backbone. This class owns only
    project inspection, deterministic validation, patch staging, and state.
    """

    def __init__(
        self,
        working_dir: str,
        builder_contract: dict[str, Any] | None = None,
        mcp_client: Any | None = None,
        fix_provider: FixProvider | None = None,
        log: Callable[[str], None] | None = None,
    ):
        self.working_dir = str(Path(working_dir).expanduser().resolve())
        self.builder_contract = builder_contract or Analyzer.default_builder_contract()
        self.mcp_client = mcp_client
        self.fix_provider = fix_provider
        self.log = log or (lambda line: None)

        self.state: dict[str, Any] = {
            "status": "new",
            "working_dir": self.working_dir,
            "findings": [],
            "plan": [],
            "patches": [],
            "validation": {},
            "scan": {},
        }

    def run_agentic_loop(
        self,
        apply_fixes: bool = False,
        max_attempts: int = 3,
        auto_setup: bool = True,
        approve: Callable[[list[dict[str, str]], int], bool] | None = None,
    ) -> dict[str, Any]:
        """SCAN -> CHECK -> PLAN -> (PATCH -> VALIDATE -> RE-SCAN) x max_attempts -> FINAL.

        Patches are only requested/applied when apply_fixes is True (explicit user approval);
        `approve(edits, attempt)` lets the GUI show the Reviewer first. The loop stops when the
        project is ready, nothing can be fixed, the provider returns nothing, or progress stalls.
        """
        self.state["attempts"] = []
        previous_signature: frozenset | None = None

        for attempt in range(1, max_attempts + 1):
            self.log(f"[agent] attempt {attempt}/{max_attempts}: scan")
            self.scan()
            self.understand()
            self.check_builder_constraint()
            self.check_wsl()
            if auto_setup and attempt == 1 and self._environment_fixable():
                self.setup_environment()
            self.check_dependencies()
            self.find_problems()
            self.build_fix_plan()
            self.validate()

            signature = frozenset((f["code"], f["file"], f["line"]) for f in self.state["findings"])
            entry: dict[str, Any] = {
                "attempt": attempt, "findings": len(self.state["findings"]),
                "validation": dict(self.state["validation"]), "patched": [], "note": "",
            }
            self.state["attempts"].append(entry)

            if self.is_ready():
                entry["note"] = "ready"
                break
            if not apply_fixes or self.fix_provider is None:
                entry["note"] = "fixes not requested" if not apply_fixes else "no fix provider (MCP offline)"
                break
            if not self._needs_code_changes():
                entry["note"] = "remaining failures are environment-related, not code"
                break
            if previous_signature is not None and signature == previous_signature:
                entry["note"] = "no progress after last patch, stopping"
                break
            previous_signature = signature

            edits = self.request_edits(attempt)
            if not edits:
                entry["note"] = "provider returned no usable edits"
                break
            if approve is not None and not approve(edits, attempt):
                entry["note"] = "edits rejected by reviewer"
                break
            patches = self.apply_patch(edits)
            entry["patched"] = [p["file"] for p in patches]
            self.log(f"[agent] patched {len(patches)} file(s)")

        self.rescan()
        self.write_report()
        return self.final_result()

    # ---- loop helpers ---------------------------------------------------
    def is_ready(self) -> bool:
        return not self.state["findings"] and bool(self.state["validation"].get("passed"))

    def _environment_fixable(self) -> bool:
        env = self.state.get("wsl_check", {})
        if env.get("ready"):
            return False
        # Can only repair if a Linux/WSL environment is actually reachable.
        return env.get("mode") in {"windows+wsl", "wsl", "linux"} and (
            bool(env.get("missing_apt")) or not env.get("buildozer_available")
            or not env.get("jdk_available") or not env.get("pygame_installed"))

    def _needs_code_changes(self) -> bool:
        v = self.state["validation"]
        return bool(self.state["findings"]) or not all(v.get(k, True) for k in ("syntax", "imports", "builder"))

    def setup_environment(self) -> dict[str, Any]:
        """Self-heal the WSL build environment (apt packages, Buildozer venv)."""
        from part1_builder.wsl_checker import apply_setup
        self.log("[agent] repairing build environment in WSL (this can take several minutes)")
        fresh = apply_setup(self.state.get("wsl_check"), log=self.log)
        self.state["wsl_check"] = fresh
        self.state["setup"] = fresh.get("setup_log", [])
        return fresh

    def request_edits(self, attempt: int) -> list[dict[str, str]]:
        validator = Validator(self.working_dir, env_status=self.state.get("wsl_check"))
        prompt = build_fix_prompt(self.state["findings"], validator.unresolved_imports(),
                                  self.state["validation"], attempt)
        try:
            files = self.fix_provider(prompt) or {}
        except Exception as exc:  # noqa: BLE001 - provider is network code
            self.log(f"[agent] fix provider failed: {exc}")
            return []
        edits = []
        for rel, content in files.items():
            if not isinstance(content, str) or not content.strip():
                continue
            if rel.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as exc:
                    self.log(f"[agent] rejected {rel}: AI output has a syntax error (line {exc.lineno})")
                    continue
            edits.append({"file": rel, "content": content})
        return edits

    def write_report(self) -> str:
        reports = Path(self.working_dir) / ".juprisx" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        path = reports / f"report-{datetime.now():%Y%m%d-%H%M%S}.json"
        keep = ("status", "attempts", "findings", "remaining_findings", "plan", "patches",
                "validation", "setup")
        data = {k: self.state.get(k) for k in keep}
        data["wsl_check"] = {k: v for k, v in self.state.get("wsl_check", {}).items() if k != "setup_log"}
        data["created_at"] = datetime.now().isoformat(timespec="seconds")
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self.state["report"] = str(path)
        return str(path)

    def scan(self):
        self.state["status"] = "scanning"
        self.state["scan"] = Analyzer(
            self.working_dir, self.builder_contract
        ).analyze()
        return self.state["scan"]

    def understand(self):
        self.state["status"] = "understanding"
        self.state["understanding"] = {
            "project_root": self.working_dir,
            "builder": self.builder_contract.get("name"),
            "immutable_builder": True,
        }
        return self.state["understanding"]

    def check_builder_constraint(self):
        self.state["builder_check"] = {
            "immutable": True,
            "rules": self.builder_contract.get("rules", []),
        }
        return self.state["builder_check"]

    def check_wsl(self):
        from part1_builder.wsl_checker import cached_check
        self.state["wsl_check"] = cached_check()
        return self.state["wsl_check"]

    def check_dependencies(self):
        validator = Validator(self.working_dir, env_status=self.state.get("wsl_check"))
        self.state["dependency_check"] = validator.validate_dependencies()
        return self.state["dependency_check"]

    def find_problems(self):
        self.state["findings"] = self.state.get("scan", {}).get("findings", [])
        self.state["status"] = "needs_fix" if self.state["findings"] else "clean"
        return self.state["findings"]

    def build_fix_plan(self):
        self.state["plan"] = Planner(self.state["findings"]).build_fix_plan()
        if self.state["plan"]:
            self.state["status"] = "plan_ready"
        return self.state["plan"]

    def apply_patch(self, edits: list[dict[str, str]] | None = None):
        if not edits:
            self.state["patches"] = []
            return self.state["patches"]

        fixer = Fixer(self.working_dir)
        patches = []
        for edit in edits:
            if edit["file"].endswith(".py"):
                ast.parse(edit["content"])  # never write a file that does not parse
            patches.append(fixer.apply_file_replacement(
                edit["file"], edit["content"]
            ))
        self.state["patches"] = patches
        self.state.setdefault("all_patches", []).extend(patches)
        self.state["status"] = "fixed"
        return patches

    def validate(self):
        self.state["validation"] = Validator(
            self.working_dir, env_status=self.state.get("wsl_check")).validate_all()
        clean = self.state["validation"].get("passed") and not self.state.get("findings")
        self.state["status"] = "validated" if clean else "needs_fix"
        return self.state["validation"]

    def rescan(self):
        self.state["rescan"] = Analyzer(
            self.working_dir, self.builder_contract
        ).analyze()
        remaining = self.state["rescan"].get("findings", [])
        self.state["remaining_findings"] = remaining
        if not remaining and self.state["validation"].get("passed"):
            self.state["status"] = "ready_to_build"
        elif remaining or not self.state["validation"].get("passed"):
            self.state["status"] = "needs_fix"
        return self.state["rescan"]

    def final_result(self):
        return self.state
