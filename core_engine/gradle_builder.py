from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class GradleBuilder:
    """Native Android Gradle builder with Windows/WSL toolchain bootstrap."""

    GRADLE_VERSION = "8.13"

    def __init__(self, project_path: str, log=lambda line: None):
        self.root = Path(project_path).expanduser().resolve()
        self.log = log

    @property
    def android_dir(self) -> Path:
        return self.root / "android"

    @staticmethod
    def _java_home() -> str | None:
        java_home = os.environ.get("JAVA_HOME") or os.environ.get("JDK_HOME")
        if java_home and (Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")).exists():
            return str(Path(java_home).resolve())
        exe = shutil.which("java.exe" if os.name == "nt" else "java") or shutil.which("java")
        if exe:
            return str(Path(exe).resolve().parent.parent)
        if os.name == "nt":
            roots = [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                Path(os.environ.get("LOCALAPPDATA", "")),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            ]
            patterns = [
                "Android/Android Studio/jbr",
                "Programs/Android Studio/jbr",
                "Java/*",
                "Eclipse Adoptium/*",
                "Microsoft/*",
                "Amazon Corretto/*",
            ]
            for root in roots:
                for pattern in patterns:
                    for candidate in root.glob(pattern):
                        if (candidate / "bin" / "java.exe").exists():
                            return str(candidate.resolve())
        return None

    @staticmethod
    def _android_sdk() -> str | None:
        for key in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            value = os.environ.get(key)
            if value and Path(value).exists():
                return str(Path(value).resolve())
        if os.name == "nt":
            candidates = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk",
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Sdk",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate.resolve())
        return None

    def _ensure_wrapper(self) -> Path | str:
        bat = self.android_dir / "gradlew.bat"
        unix = self.android_dir / "gradlew"
        if os.name == "nt" and bat.exists():
            return bat
        if unix.exists():
            return unix
        found = shutil.which("gradle")
        if found:
            self.log("[gradle] generating wrapper from installed Gradle")
            subprocess.run([found, "wrapper", f"--gradle-version={self.GRADLE_VERSION}"], cwd=self.android_dir, check=True)
            if bat.exists() or unix.exists():
                return bat if os.name == "nt" and bat.exists() else unix

        # Windows installations commonly keep Gradle only inside WSL. Generate
        # the wrapper there against the same project mounted at /mnt/<drive>/...
        if os.name == "nt":
            try:
                from part1_builder.wsl_connector import run_command
                win = self.android_dir.resolve().as_posix()
                if len(win) > 1 and win[1] == ":":
                    wsl_dir = f"/mnt/{win[0].lower()}/{win[2:].lstrip('/')}"
                    cmd = f"cd {self._quote(wsl_dir)} && command -v gradle >/dev/null 2>&1 && gradle wrapper --gradle-version {self.GRADLE_VERSION}"
                    rc, out, err = run_command(cmd, timeout=180)
                    if rc == 0 and bat.exists():
                        self.log("[gradle] wrapper generated through WSL Gradle")
                        return bat
            except Exception as exc:
                self.log(f"[gradle] WSL wrapper bootstrap skipped: {exc}")
        raise FileNotFoundError(
            "Gradle wrapper is missing and no Gradle installation was found. "
            "Install Gradle once in WSL (or Windows), then rerun the build."
        )

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"

    def build(self, artifact: str = "both") -> dict:
        android = self.android_dir
        if not (android / "settings.gradle").exists() and not (android / "settings.gradle.kts").exists():
            raise FileNotFoundError("Native Android template is missing: android/settings.gradle")
        java_home = self._java_home()
        if not java_home:
            raise FileNotFoundError("JDK/keytool not found. Set JAVA_HOME or install a JDK/Android Studio.")
        sdk = self._android_sdk()
        if not sdk:
            raise FileNotFoundError("Android SDK not found. Set ANDROID_SDK_ROOT/ANDROID_HOME or install the Android SDK.")
        gradle = self._ensure_wrapper()
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
        env["ANDROID_SDK_ROOT"] = sdk
        env["ANDROID_HOME"] = sdk
        env["PATH"] = str(Path(java_home) / "bin") + os.pathsep + env.get("PATH", "")
        for kind, task in commands:
            self.log(f"[gradle] {Path(str(gradle)).name} {task}")
            proc = subprocess.run([str(gradle), task], cwd=android, env=env,
                                  capture_output=True, text=True,
                                  shell=(os.name == "nt" and str(gradle).endswith(".bat")))
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
