from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GradleBuilder:
    """Headless Android Gradle builder for the generated native WebView container."""

    def __init__(self, project_path: str, log=lambda line: None):
        self.root = Path(project_path).expanduser().resolve()
        self.log = log

    @property
    def gradle(self) -> Path:
        wrapper = self.root / "android" / "gradlew"
        return wrapper if wrapper.exists() else Path("gradle")

    def build(self, artifact: str = "both") -> dict:
        android = self.root / "android"
        if not (android / "settings.gradle").exists() and not (android / "settings.gradle.kts").exists():
            raise FileNotFoundError("Native Android template is missing: android/settings.gradle")
        commands = []
        if artifact in {"apk", "both"}:
            commands.append(("apk", "assembleRelease"))
        if artifact in {"aab", "both"}:
            commands.append(("aab", "bundleRelease"))
        outputs = {}
        for kind, task in commands:
            self.log(f"[gradle] ./gradlew {task}")
            cmd = [str(self.gradle), task]
            proc = subprocess.run(cmd, cwd=android, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"Gradle {task} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
            ext = "apk" if kind == "apk" else "aab"
            candidates = sorted(android.rglob(f"*.{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                raise RuntimeError(f"Gradle completed but no .{ext} artifact was produced.")
            outputs[kind] = str(candidates[0])
            self.log(f"[gradle] {kind.upper()}: {candidates[0]}")
        return outputs

    @staticmethod
    def ensure_wrapper(android_dir: str) -> bool:
        return shutil.which("gradle") is not None or (Path(android_dir) / "gradlew").exists()
