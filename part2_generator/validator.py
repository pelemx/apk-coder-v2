from __future__ import annotations

from pathlib import Path
from typing import Any

from core_engine.web_validator import WebValidator


class Validator:
    """Deterministic validation for generated HTML/JS Android WebView projects."""

    def __init__(self, project_path: str, expected_python: str | None = None,
                 env_status: dict[str, Any] | None = None):
        self.project_path = Path(project_path).expanduser().resolve()

    def _web(self) -> dict[str, Any]:
        return WebValidator(str(self.project_path)).validate()

    def validate_syntax(self) -> bool:
        result = self._web()
        return not any(f["code"] in {"MANIFEST_JSON", "BROKEN_ASSET", "MISSING_ENTRY"} for f in result["findings"])

    def validate_imports(self) -> bool:
        return not any(f["code"] == "REMOTE_DEPENDENCY" for f in self._web()["findings"])

    def validate_dependencies(self) -> bool:
        findings = self._web()["findings"]
        return not any(f["code"] in {"REMOTE_DEPENDENCY", "REMOTE_SCRIPT", "INSECURE_RESOURCE"} for f in findings)

    def validate_builder_constraints(self) -> bool:
        findings = self._web()["findings"]
        return not any(f["severity"] == "HIGH" for f in findings)

    def validate_wsl(self) -> bool:
        return True

    def validate_pygame(self) -> bool:
        return True

    def unresolved_imports(self) -> list[dict[str, Any]]:
        return []

    def validate_all(self) -> dict[str, Any]:
        web = self._web()
        high = any(f["severity"] == "HIGH" for f in web["findings"])
        results = {
            "syntax": self.validate_syntax(),
            "imports": self.validate_imports(),
            "pygame": True,
            "wsl": True,
            "builder": not high,
            "dependencies": self.validate_dependencies(),
            "web": not high,
        }
        results["passed"] = all(results.values())
        results["findings"] = web["findings"]
        return results
