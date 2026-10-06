from __future__ import annotations

from pathlib import Path
from typing import Any

from core_engine.web_validator import WebValidator


class Validator:
    """Deterministic validation for HTML/JS/CSS Android WebView projects."""

    def __init__(self, project_path: str, expected_python: str | None = None,
                 env_status: dict[str, Any] | None = None):
        self.project_path = Path(project_path).expanduser().resolve()
        self.env_status = env_status or {}

    def _web(self) -> dict[str, Any]:
        return WebValidator(str(self.project_path)).validate()

    def validate_syntax(self) -> bool:
        findings = self._web()["findings"]
        return not any(f["code"] in {"MANIFEST_JSON", "BROKEN_ASSET", "MISSING_ENTRY"} for f in findings)

    def validate_imports(self) -> bool:
        findings = self._web()["findings"]
        return not any(f["code"] in {"REMOTE_DEPENDENCY", "REMOTE_SCRIPT"} for f in findings)

    def validate_dependencies(self) -> bool:
        findings = self._web()["findings"]
        return not any(f["code"] in {"REMOTE_DEPENDENCY", "REMOTE_SCRIPT", "INSECURE_RESOURCE", "REMOTE_OR_FILE_URL"} for f in findings)

    def validate_web(self) -> bool:
        return not any(f["severity"] == "HIGH" for f in self._web()["findings"])

    def validate_builder_constraints(self) -> bool:
        return self.validate_web()

    def validate_wsl(self) -> bool:
        # Environment is checked by the build layer; source validation must remain runnable offline.
        return bool(self.env_status.get("ready", True))

    def unresolved_imports(self) -> list[dict[str, Any]]:
        return []

    def validate_all(self) -> dict[str, Any]:
        web = self._web()
        high = any(f["severity"] == "HIGH" for f in web["findings"])
        results = {
            "syntax": self.validate_syntax(),
            "imports": self.validate_imports(),
            "web": not high,
            "dependencies": self.validate_dependencies(),
            "builder": not high,
            "wsl": self.validate_wsl(),
        }
        results["passed"] = all(results.values())
        results["findings"] = web["findings"]
        return results
