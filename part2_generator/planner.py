from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlanStep:
    id: str
    finding_code: str
    action: str
    file: str
    line: int
    risk: str = "medium"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "finding_code": self.finding_code,
            "action": self.action,
            "file": self.file,
            "line": self.line,
            "risk": self.risk,
        }


class Planner:
    """Converts analyzer findings into explicit, reviewable fix steps."""

    ACTIONS = {
        "HOST_DEPENDENT_FONT": "Replace SysFont usage with a bundled project-relative font.",
        "WINDOWS_ABSOLUTE_PATH": "Replace the hardcoded Windows path with a pathlib project-relative path.",
        "ABSOLUTE_PATH": "Replace the absolute path with a project-relative path.",
        "WINDOWS_ONLY_IMPORT": "Replace the Windows-only API with a WSL/Linux-compatible implementation.",
        "WINDOWS_ONLY_DEPENDENCY": "Remove or replace the Windows-only dependency.",
        
        # PERBAIKAN: Hapus saran pygame.SCALED karena bikin crash di Android
        "BUILDER_MANAGED_DISPLAY": "Make set_mode adapt to the device screen by using size (0, 0) or querying pygame.display.Info(). CRITICAL: NEVER use pygame.SCALED, it crashes on Android.",
        
        "PYTHON_SYNTAX_ERROR": "Repair the syntax error before any other source modification.",
        "BUILDOZER_EXTENSIONS_UNDECLARED": "Add the required project asset/source extensions to buildozer.spec.",
    }

    def __init__(self, findings: list[dict[str, Any]] | None = None):
        self.findings = findings or []

    def build_fix_plan(self) -> list[dict[str, Any]]:
        plan = []
        for index, finding in enumerate(self.findings, 1):
            code = finding.get("code", "")
            action = finding.get("recommended_action") or self.ACTIONS.get(code)
            if not action:
                action = "Review finding manually before modification."

            severity = str(finding.get("severity", "LOW")).upper()
            risk = "high" if severity == "HIGH" else "medium" if severity == "MED" else "low"

            plan.append(PlanStep(
                id=f"FIX-{index:03d}",
                finding_code=code,
                action=action,
                file=finding.get("file", ""),
                line=int(finding.get("line", 0) or 0),
                risk=risk,
            ).as_dict())
        return plan
