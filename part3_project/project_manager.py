"""
Project data layer.

Each project keeps its state in   <working_dir>/.juprisx/project.json
A small registry in               <workspace>/registry.json
maps project_id -> working_dir so the Project Table can list everything.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .workflow import InvalidTransition, Workflow, WorkflowState

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

VALIDATION_KEYS = ("syntax", "imports", "pygame", "wsl", "builder")
SEVERITY_ORDER = {"HIGH": 0, "MED": 1, "LOW": 2}


def safe_rel_path(rel: str) -> str:
    """Normalize a project-relative path. Rejects absolute paths, drive letters,
    '..' escapes and the .juprisx metadata folder."""
    rel = str(rel).replace("\\", "/").strip()
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise ValueError(f"Invalid project path: {rel!r}")
    if ".." in parts or parts[0] == ".juprisx":
        raise ValueError(f"Invalid project path: {rel!r}")
    return "/".join(parts)


# --------------------------------------------------------------------------
# Secret handling (keystore passwords)
# --------------------------------------------------------------------------
class SecretBox:
    """Encrypts keystore passwords. Uses Fernet if `cryptography` is installed,
    otherwise falls back to obfuscation (clearly marked with a different prefix)."""

    def __init__(self, key_file: Path):
        self.key_file = key_file
        self._fernet = None
        try:
            from cryptography.fernet import Fernet
            if key_file.exists():
                key = key_file.read_bytes()
            else:
                key = Fernet.generate_key()
                key_file.parent.mkdir(parents=True, exist_ok=True)
                key_file.write_bytes(key)
                try:
                    os.chmod(key_file, 0o600)
                except OSError:
                    pass
            self._fernet = Fernet(key)
        except ImportError:
            self._fernet = None

    def encrypt(self, text: str) -> str:
        if not text:
            return ""
        if self._fernet:
            return "fernet:" + self._fernet.encrypt(text.encode()).decode()
        return "b64:" + base64.b64encode(text.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        if token.startswith("fernet:"):
            if not self._fernet:
                raise RuntimeError("Password is Fernet-encrypted but 'cryptography' is not installed.")
            return self._fernet.decrypt(token[7:].encode()).decode()
        if token.startswith("b64:"):
            return base64.b64decode(token[4:]).decode()
        return token  # legacy plaintext


# --------------------------------------------------------------------------
# Project manager
# --------------------------------------------------------------------------
class ProjectManager:
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.workspace_path / "registry.json"
        self.secrets = SecretBox(self.workspace_path / ".secret.key")

    # ---- paths ----------------------------------------------------------
    @staticmethod
    def project_file(working_dir: str) -> Path:
        return Path(working_dir) / ".juprisx" / "project.json"

    # ---- registry -------------------------------------------------------
    def _read_registry(self) -> dict[str, str]:
        if self.registry_path.exists():
            try:
                return json.loads(self.registry_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_registry(self, reg: dict[str, str]):
        self._atomic_write(self.registry_path, reg)

    @staticmethod
    def _atomic_write(path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    # ---- CRUD -----------------------------------------------------------
    def create_project(self, name: str, working_dir: str, save: bool = True) -> dict:
        working_dir = str(Path(working_dir).expanduser().resolve())
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        now = datetime.now().isoformat(timespec="seconds")

        project = {
            "project_id": str(uuid.uuid4()),
            "name": name,
            "created_at": now,
            "working_dir": working_dir,
            "status": WorkflowState.NEW.value,
            "last_scan": None,
            "keystore": {
                "path": "", "alias": "", "store_password": "",
                "key_password": "", "generated_at": None,
            },
            "findings": [],
            "plan": [],
            "patches_applied": [],
            "validation": {k: False for k in VALIDATION_KEYS},
            "build": {"apk": None, "aab": None, "last_build": None},
            "assets": {"icon": None, "feature_graphic": None, "screenshots": []},
            "history": [],
        }
        if save:
            self.save_project(project)
        return project

    def save_project(self, project: dict, file_path: str | None = None):
        """Save project JSON. Default location is <working_dir>/.juprisx/project.json
        and the project is (re)registered."""
        if file_path:
            self._atomic_write(Path(file_path), project)
            return
        wd = project.get("working_dir")
        if not wd:
            raise ValueError("Project has no working_dir")
        self._atomic_write(self.project_file(wd), project)
        reg = self._read_registry()
        if reg.get(project["project_id"]) != wd:
            reg[project["project_id"]] = wd
            self._write_registry(reg)

    def load_project(self, file_path: str) -> dict:
        p = Path(file_path)
        if p.is_dir():
            p = self.project_file(str(p))
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def get_project(self, project_id: str) -> dict:
        wd = self._read_registry().get(project_id)
        return self.load_project(wd) if wd else {}

    def list_projects(self) -> list[dict]:
        """All registered projects. Entries whose folder vanished are kept but
        marked status='missing' (never silently dropped)."""
        out = []
        for pid, wd in self._read_registry().items():
            proj = self.load_project(wd)
            if proj:
                out.append(proj)
            else:
                out.append({"project_id": pid, "name": Path(wd).name or pid,
                            "working_dir": wd, "status": "missing", "last_scan": None})
        out.sort(key=lambda p: p.get("created_at") or "")
        return out

    def create_project_with_files(self, name: str, working_dir: str,
                                  files: dict[str, str]) -> dict:
        """Create a project and write its initial files (e.g. generated from chat).
        Never overwrites an existing file; raises FileExistsError instead."""
        root = Path(working_dir).expanduser().resolve()
        safe = {safe_rel_path(k): v for k, v in files.items()}
        clashes = [k for k in safe if (root / k).exists()]
        if clashes:
            raise FileExistsError("Would overwrite: " + ", ".join(clashes))
        root.mkdir(parents=True, exist_ok=True)
        for rel, content in safe.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return self.create_project(name, str(root))

    def import_project(self, working_dir: str, name: str | None = None) -> dict:
        """Register an existing folder. Reuses its project.json if present."""
        working_dir = str(Path(working_dir).expanduser().resolve())
        existing = self.load_project(working_dir)
        if existing:
            existing["working_dir"] = working_dir
            self.save_project(existing)
            return existing
        return self.create_project(name or Path(working_dir).name, working_dir)

    def delete_project(self, project_id: str, delete_files: bool = False) -> bool:
        """Remove from registry. Only deletes the .juprisx metadata folder when
        delete_files=True; user source code is never removed."""
        reg = self._read_registry()
        wd = reg.pop(project_id, None)
        if wd is None:
            return False
        self._write_registry(reg)
        if delete_files:
            import shutil
            shutil.rmtree(Path(wd) / ".juprisx", ignore_errors=True)
        return True

    # ---- workflow -------------------------------------------------------
    def set_status(self, project: dict, new_state: WorkflowState | str, note: str = "",
                   save: bool = True) -> dict:
        wf = Workflow(project.get("status", "new"), project.get("history"))
        wf.transition_to(new_state, note)  # raises InvalidTransition
        project["status"] = wf.value
        project["history"] = wf.history
        if save:
            self.save_project(project)
        return project

    # ---- pipeline operations -------------------------------------------
    def scan(self, project: dict) -> dict:
        """SCAN -> findings + plan + validation, and move the workflow along."""
        from part2_generator.agent_client import AgentClient

        wd = project["working_dir"]
        self.set_status(project, WorkflowState.SCANNING, "scan started", save=False)

        agent = AgentClient(wd)
        agent.scan()
        agent.find_problems()
        agent.build_fix_plan()
        validation = agent.validate()

        project["findings"] = [self._relativize(f, wd) for f in agent.state["findings"]]
        project["findings"].sort(key=lambda f: SEVERITY_ORDER.get(str(f.get("severity")).upper(), 9))
        project["plan"] = [self._relativize(s, wd) for s in agent.state["plan"]]
        project["validation"] = {k: bool(validation.get(k)) for k in VALIDATION_KEYS}
        project["validation"]["dependencies"] = bool(validation.get("dependencies", True))
        project["last_scan"] = datetime.now().isoformat(timespec="seconds")

        if project["findings"]:
            self.set_status(project, WorkflowState.NEEDS_FIX,
                            f"{len(project['findings'])} findings", save=False)
            self.set_status(project, WorkflowState.PLAN_READY, "fix plan built", save=False)
        elif validation.get("passed"):
            self.set_status(project, WorkflowState.VALIDATED, "no findings, validation passed", save=False)
            self.set_status(project, WorkflowState.READY_TO_BUILD, "all checks passed", save=False)
        else:
            failed = [k for k, v in project["validation"].items() if not v]
            self.set_status(project, WorkflowState.NEEDS_FIX,
                            "validation failed: " + ", ".join(failed), save=False)
        self.save_project(project)
        return project

    def agentic_fix(self, project: dict, fix_provider, max_attempts: int = 3, log=None) -> dict:
        """Run the bounded fix -> validate -> re-scan loop (user pressed Auto-fix = approval).
        Every change is backed up by Fixer and can be rolled back from the Reviewer."""
        from part2_generator.agent_client import AgentClient

        wd = project["working_dir"]
        agent = AgentClient(wd, fix_provider=fix_provider, log=log)
        agent.run_agentic_loop(apply_fixes=True, max_attempts=max_attempts)

        patches = []
        for p in agent.state.get("all_patches", []):
            p = dict(p)
            p["applied_at"] = datetime.now().isoformat(timespec="seconds")
            p["file"] = self._rel(p["file"], wd)
            p["backup"] = self._rel(p["backup"], wd)
            patches.append(p)
        if patches:
            project.setdefault("patches_applied", []).extend(patches)
            if project["status"] == WorkflowState.PLAN_READY.value:
                self.set_status(project, WorkflowState.FIXED, f"{len(patches)} file(s) patched by agent", save=False)
        project["agent_attempts"] = agent.state.get("attempts", [])
        project["agent_report"] = self._rel(agent.state.get("report", ""), wd) if agent.state.get("report") else None
        return self.scan(project)  # authoritative findings/validation/workflow state

    def apply_edits(self, project: dict, edits: list[dict[str, str]]) -> list[dict]:
        """Apply approved edits [{'file': rel_path, 'content': str}] with backup,
        then re-validate. Moves PLAN_READY -> FIXED -> VALIDATED (-> READY_TO_BUILD)."""
        from part2_generator.fixer import Fixer
        from part2_generator.validator import Validator

        if not edits:
            raise ValueError("No edits to apply")
        fixer = Fixer(project["working_dir"])
        patches = [fixer.apply_file_replacement(e["file"], e["content"]) for e in edits]
        for p in patches:
            p["applied_at"] = datetime.now().isoformat(timespec="seconds")
            p["file"] = self._rel(p["file"], project["working_dir"])
            p["backup"] = self._rel(p["backup"], project["working_dir"])
        project.setdefault("patches_applied", []).extend(patches)

        if project["status"] != WorkflowState.FIXED.value:
            self.set_status(project, WorkflowState.FIXED, f"{len(patches)} file(s) patched", save=False)

        validation = Validator(project["working_dir"]).validate_all()
        project["validation"] = {k: bool(validation.get(k)) for k in VALIDATION_KEYS}
        project["validation"]["dependencies"] = bool(validation.get("dependencies", True))
        self.save_project(project)
        return patches

    def finalize_validation(self, project: dict) -> dict:
        """After fixing: re-scan; ready_to_build only if clean AND validation passed."""
        return self.scan(project)

    def rollback(self, project: dict, files: list[str] | None = None) -> list[dict]:
        """Restore backups for given files (default: every patched file)."""
        from part2_generator.fixer import Fixer

        fixer = Fixer(project["working_dir"])
        targets = files or sorted({p["file"] for p in project.get("patches_applied", [])})
        results = []
        for rel in targets:
            try:
                results.append(fixer.rollback_file(rel))
            except FileNotFoundError as exc:
                results.append({"status": "no_backup", "file": rel, "error": str(exc)})
        rolled = {self._rel(r["file"], project["working_dir"])
                  for r in results if r.get("status") == "rolled_back"}
        project["patches_applied"] = [
            p for p in project.get("patches_applied", []) if p["file"] not in rolled
        ]
        if project["status"] not in (WorkflowState.NEEDS_FIX.value, WorkflowState.NEW.value):
            try:
                self.set_status(project, WorkflowState.NEEDS_FIX, "rollback", save=False)
            except InvalidTransition:
                pass
        project["validation"] = {k: False for k in VALIDATION_KEYS}
        self.save_project(project)
        return results

    # ---- keystore -------------------------------------------------------
    def set_keystore(self, project: dict, path: str, alias: str,
                     store_password: str, key_password: str,
                     generated_at: str | None = None):
        project["keystore"] = {
            "path": path,
            "alias": alias,
            "store_password": self.secrets.encrypt(store_password),
            "key_password": self.secrets.encrypt(key_password),
            "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        }
        self.save_project(project)

    def get_keystore(self, project: dict) -> dict:
        """Keystore info with passwords decrypted (for the compiler only; never log this)."""
        ks = dict(project.get("keystore", {}))
        if ks.get("path") and not Path(ks["path"]).is_absolute():
            ks["path"] = str(Path(project["working_dir"]) / ks["path"])
        ks["store_password"] = self.secrets.decrypt(ks.get("store_password", ""))
        ks["key_password"] = self.secrets.decrypt(ks.get("key_password", ""))
        return ks

    # ---- Play Store assets ---------------------------------------------
    def record_asset(self, project: dict, kind: str, path: str):
        """Remember a saved Play Store asset (paths stored project-relative)."""
        assets = project.setdefault(
            "assets", {"icon": None, "feature_graphic": None, "screenshots": []})
        rel = self._rel(path, project["working_dir"])
        if kind == "screenshot":
            if rel not in assets["screenshots"]:
                assets["screenshots"].append(rel)
        elif kind in ("icon", "feature_graphic"):
            assets[kind] = rel
        else:
            raise ValueError(f"Unknown asset kind: {kind}")
        self.save_project(project)

    # ---- build bookkeeping ---------------------------------------------
    def record_build(self, project: dict, result: dict):
        """Store a CompilerPipeline.run_compile() result."""
        now = datetime.now().isoformat(timespec="seconds")
        project["build"]["last_build"] = now
        if result.get("status") == "success":
            project["build"]["apk"] = result.get("apk")
            project["build"]["aab"] = result.get("aab")
            self.set_status(project, WorkflowState.PLAYSTORE_READY, "build ok", save=False)
        else:
            project["build"]["error"] = result.get("message")
            self.set_status(project, WorkflowState.READY_TO_BUILD, "build failed", save=False)
        self.save_project(project)

    def start_build(self, project: dict):
        if project["status"] != WorkflowState.READY_TO_BUILD.value:
            raise InvalidTransition("Project must be ready_to_build before building")
        if not project.get("keystore", {}).get("path"):
            raise ValueError("No keystore configured for this project")
        self.set_status(project, WorkflowState.BUILDING, "build started")

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _rel(path: str, wd: str) -> str:
        try:
            return Path(path).resolve().relative_to(Path(wd).resolve()).as_posix()
        except (ValueError, OSError):
            return str(path)

    @classmethod
    def _relativize(cls, item: dict, wd: str) -> dict:
        item = dict(item)
        if item.get("file"):
            item["file"] = cls._rel(item["file"], wd)
        return item
