from __future__ import annotations

import json
import re
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
        if www.exists(): shutil.rmtree(www)
        shutil.copytree(web, www)

        manifest = web / "manifest.json"
        meta = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
        app_name = str(meta.get("name") or self.project_dir.name)
        package = str(meta.get("package") or f"com.juprisx.{self._slug(app_name)}")
        gradle = android / "app" / "build.gradle"
        gradle.write_text(gradle.read_text(encoding="utf-8").replace("__APPLICATION_ID__", package), encoding="utf-8")
        native_manifest = android / "app" / "src" / "main" / "AndroidManifest.xml"
        native_manifest.write_text(native_manifest.read_text(encoding="utf-8").replace("__APP_LABEL__", app_name.replace('"', "")), encoding="utf-8")
        return {"android": str(android), "web_assets": str(www), "application_id": package, "app_name": app_name}

    def _write_signing_properties(self, ks: dict) -> None:
        if not ks.get("path") or not ks.get("alias") or not ks.get("store_password") or not ks.get("key_password"):
            raise ValueError("Complete signing information is required for a release build.")
        signing = self.project_dir / "signing"
        signing.mkdir(parents=True, exist_ok=True)
        target = signing / "signing.properties"
        target.write_text(
            "storeFile=" + str(Path(ks["path"]).resolve()) + "\n" +
            "storePassword=" + ks["store_password"] + "\n" +
            "keyAlias=" + ks["alias"] + "\n" +
            "keyPassword=" + ks["key_password"] + "\n",
            encoding="utf-8",
        )

    def validate_web(self):
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
            self._write_signing_properties(ks)
            outputs = GradleBuilder(str(self.project_dir), log=self.log).build(artifact)
            return {"status": "success", "apk": outputs.get("apk"), "aab": outputs.get("aab"), "keystore": ks.get("path"), "android": android_info, "validation": validation}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "validation": validation}

    def run_compile_apk(self): return self.run_compile("apk")
    def run_compile_aab(self): return self.run_compile("aab")

    def prepare_buildozer_spec(self):
        return {"status": "deprecated", "message": "Buildozer/p4a is disabled for HTML/JS projects."}

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "app"
