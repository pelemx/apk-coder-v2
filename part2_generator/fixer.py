from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Any


class Fixer:
    """
    Safe local patch helper.

    It intentionally does not invent source-code changes from a finding.
    AI-generated edits must arrive as explicit file patches. Every modified
    file is backed up before replacement.
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).expanduser().resolve()
        self.meta_dir = self.project_path / ".juprisx"
        self.backup_dir = self.meta_dir / "backup"
        self.patch_dir = self.meta_dir / "patches"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.patch_dir.mkdir(parents=True, exist_ok=True)

    def apply_file_replacement(self, relative_path: str, new_content: str) -> dict[str, Any]:
        target = self._safe_target(relative_path)
        if target.exists() and not target.is_file():
            raise ValueError(f"Target is not a file: {relative_path}")

        existed = target.exists()
        old_content = target.read_text(encoding="utf-8") if existed else ""
        self._backup(target)
        if not existed:
            # Remember that this file did not exist, so rollback can remove it again.
            marker = self._created_marker(target)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("created by JuprisX agent\n", encoding="utf-8")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")

        rel = target.relative_to(self.project_path).as_posix()
        diff = "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{rel}" if existed else "/dev/null",
            tofile=f"b/{rel}",
        ))
        patch_file = self.patch_dir / (rel.replace("/", "__") + ".diff")
        patch_file.write_text(diff, encoding="utf-8")

        return {
            "file": str(target),
            "changed": old_content != new_content,
            "patch": str(patch_file),
            "backup": str(self.backup_dir / target.relative_to(self.project_path)),
        }

    def apply_patch(self, diff_content: str):
        """
        Store an externally generated unified diff for review.

        Applying arbitrary unified diffs is intentionally not implemented here;
        the agent must first parse/approve concrete file edits and call
        apply_file_replacement(). This prevents accidental project-wide rewrites.
        """
        if not diff_content or not diff_content.strip():
            raise ValueError("diff_content is empty")
        patch_path = self.patch_dir / "pending.patch"
        patch_path.write_text(diff_content, encoding="utf-8")
        return {
            "status": "pending_review",
            "patch": str(patch_path),
            "message": "Patch stored; no source file was modified.",
        }

    def rollback_file(self, relative_path: str) -> dict[str, Any]:
        target = self._safe_target(relative_path)
        marker = self._created_marker(target)
        if marker.exists():
            if target.exists():
                target.unlink()
            marker.unlink()
            return {"status": "rolled_back", "file": str(target), "removed_new_file": True}
        backup = self.backup_dir / target.relative_to(self.project_path)
        if not backup.exists():
            raise FileNotFoundError(f"No backup exists for {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        return {"status": "rolled_back", "file": str(target)}

    def _created_marker(self, target: Path) -> Path:
        return self.backup_dir / (target.relative_to(self.project_path).as_posix() + ".__created__")

    def _backup(self, target: Path):
        if not target.exists():
            return
        relative = target.relative_to(self.project_path)
        backup = self.backup_dir / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(target, backup)

    def _safe_target(self, relative_path: str) -> Path:
        candidate = (self.project_path / relative_path).resolve()
        try:
            candidate.relative_to(self.project_path)
        except ValueError as exc:
            raise ValueError(f"Path escapes project root: {relative_path}") from exc
        return candidate
