from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class GradleBuilder:
    """Headless native Android Gradle builder; no Buildozer/p4a/WSL dependency."""

    def __init__(self, project_path: str, log=lambda line: None):
        self.root = Path(project_path).expanduser().resolve()
        self.log = log

    @property
    def android_dir(self) -> Path:
        return self.root / "android"

    @property
    def gradle(self) -> Path | str:
        bat = self.android_dir / "gradlew.bat"
        unix = self.android_dir / "gradlew"
        if os.name == "nt" and bat.exists():
            return bat
        if unix.exists():
            return unix
        found = shutil.which("gradle")
        if found:
            return found
        raise FileNotFoundError(
            "Gradle wrapper is missing. Expected android/gradlew.bat (Windows) or android/gradlew."
        )

    @staticmethod
    def ensure_java() -> str:
        """Resolve a JDK without WSL; Android Studio's bundled JBR is supported."""
        java_home = os.environ.get("JAVA_HOME")
        if java_home and (Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")).exists():
            return java_home
        java = shutil.which("java.exe" if os.name == "nt" else "java") or shutil.which("java")
        if java:
            return str(Path(java).resolve().parent.parent)
        if os.name == "nt":
            candidates = [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Android Studio" / "jbr",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "jbr",
            ]
            for candidate in candidates:
                if (candidate / "bin" / "java.exe").exists():
                    return str(candidate)
        raise FileNotFoundError(
            "Java JDK not found. Install Android Studio/JDK or set JAVA_HOME. "
            "HTML/JS Android builds no longer use Buildozer or WSL."
        )

    def build(self, artifact: str = "both") -> dict:
        android = self.android_dir
        if not (android / "settings.gradle").exists() and not (android / "settings.gradle.kts").exists():
            raise FileNotFoundError("Native Android template is missing: android/settings.gradle")
        java_home = self.ensure_java()
        commands = []
        if artifact in {"apk", "both"}:
            commands.append(("apk", "assembleRelease"))
        if artifact in {"aab", "both"}:
            commands.append(("aab", "bundleRelease"))
        if not commands:
            raise ValueError(f"Unsupported artifact: {artifact}")

        outputs = {}
        env = os.environ.copy()
        env["JAVA_HOME"] = java_home
        env["PATH"] = str(Path(java_home) / "bin") + os.pathsep + env.get("PATH", "")
        gradle = self.gradle
        for kind, task in commands:
            self.log(f"[gradle] {Path(str(gradle)).name} {task}")
            proc = subprocess.run([str(gradle), task], cwd=android, env=env,
                                  capture_output=True, text=True, shell=(os.name == "nt" and str(gradle).endswith(".bat")))
            if proc.returncode != 0:
                raise RuntimeError(f"Gradle {task} failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}")
            ext = "apk" if kind == "apk" else "aab"
            candidates = sorted(android.rglob(f"*.{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                raise RuntimeError(f"Gradle completed but no .{ext} artifact was produced.")
            outputs[kind] = str(candidates[0])
            self.log(f"[gradle] {kind.upper()}: {candidates[0]}")
        return outputs

    @staticmethod
    def ensure_wrapper(android_dir: str) -> bool:
        root = Path(android_dir)
        return (root / "gradlew.bat").exists() or (root / "gradlew").exists() or shutil.which("gradle") is not None
