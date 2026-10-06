from __future__ import annotations

import json
import shutil
from pathlib import Path

from core_engine.gradle_builder import GradleBuilder
from core_engine.keystore_manager import KeystoreManager
from core_engine.web_validator import WebValidator


class CompilerPipeline:
    """HTML/JS -> native Android WebView -> signed APK/AAB pipeline."""

    def __init__(self, project_dir: str, keystore_info: dict | None = None, log=lambda line: None):
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.keystore_info = keystore_info or {}
        self.log = log

    def prepare_android_project(self) -> dict:
        template = Path(__file__).resolve().parent.parent / "templates" / "android_webview"
        android = self.project_dir / "android"
        if not template.exists():
            raise FileNotFoundError(f"Android WebView template missing: {template}")
        if not android.exists():
            shutil.copytree(template, android)
        web = self.project_dir / "web"
        if not (web / "index.html").exists():
            raise FileNotFoundError(f"Missing web entry point: {web / 'index.html'}")
        www = android / "app" / "src" / "main" / "assets" / "www"
        if www.exists():
            shutil.rmtree(www)
        shutil.copytree(web, www)
        return {"android": str(android), "web_assets": str(www)}

    def validate_web(self) -> dict:
        return WebValidator(str(self.project_dir)).validate()

    def run_compile(self, artifact: str = "both") -> dict:
        validation = self.validate_web()
        if validation.get("status") == "failed":
            return {"status": "error", "message": "Web validation failed.", "validation": validation}
        try:
            android_info = self.prepare_android_project()
            ks = self.keystore_info
            if not ks.get("path"):
                ks = KeystoreManager(str(self.project_dir)).ensure()
            outputs = GradleBuilder(str(self.project_dir), log=self.log).build(artifact)
            return {
                "status": "success",
                "apk": outputs.get("apk"),
                "aab": outputs.get("aab"),
                "keystore": ks.get("path"),
                "android": android_info,
                "validation": validation,
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "validation": validation}

    def run_compile_apk(self) -> dict:
        return self.run_compile("apk")

    def run_compile_aab(self) -> dict:
        return self.run_compile("aab")

    def prepare_buildozer_spec(self) -> dict:
        """Compatibility shim: Buildozer is no longer part of the HTML/JS packaging path."""
        return {"status": "deprecated", "message": "Buildozer/p4a is disabled for HTML/JS projects. Use the native Android WebView Gradle pipeline."}
