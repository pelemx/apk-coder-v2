from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class GradleBuilder:
    """Native Android Gradle builder with Windows + WSL toolchain fallback."""

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
            roots = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")), Path(os.environ.get("LOCALAPPDATA", "")), Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))]
            for root in roots:
                for pattern in ("Android/Android Studio/jbr", "Programs/Android Studio/jbr", "Java/*", "Eclipse Adoptium/*", "Microsoft/*", "Amazon Corretto/*"):
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
            for candidate in (Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk", Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Sdk"):
                if candidate.exists():
                    return str(candidate.resolve())
        return None

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"

    def _wsl_dir(self) -> str:
        win = self.android_dir.resolve().as_posix()
        if len(win) < 2 or win[1] != ":":
            raise RuntimeError("WSL fallback requires the project to be on a Windows drive.")
        return f"/mnt/{win[0].lower()}/{win[2:].lstrip('/')}"

    def _wsl_toolchain(self) -> str:
        """Return a minimal Linux toolchain bootstrap command.

        The command deliberately avoids inheriting the huge Windows PATH from WSL.
        """
        gradle_root = f"$HOME/.juprisx/tools/gradle-{self.GRADLE_VERSION}"
        return (
            "set -e; "
            "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
            "if ! command -v java >/dev/null 2>&1; then "
            "sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-21-jdk unzip curl; "
            "fi; "
            "if [ ! -x " + gradle_root + "/bin/gradle ]; then "
            "mkdir -p $HOME/.juprisx/tools; "
            f"curl -fsSL https://services.gradle.org/distributions/gradle-{self.GRADLE_VERSION}-bin.zip -o $HOME/.juprisx/tools/gradle.zip; "
            "rm -rf $HOME/.juprisx/tools/gradle-*; "
            "unzip -q $HOME/.juprisx/tools/gradle.zip -d $HOME/.juprisx/tools; "
            "rm -f $HOME/.juprisx/tools/gradle.zip; "
            "fi; "
            f"export PATH={gradle_root}/bin:$PATH; "
            "export JAVA_HOME=${JAVA_HOME:-$(dirname $(dirname $(readlink -f $(command -v java))))}; "
            "export ANDROID_SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}; "
        )

    def _ensure_wrapper(self) -> Path | str | None:
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
        if os.name == "nt":
            try:
                from part1_builder.wsl_connector import run_command
                wsl_dir = self._wsl_dir()
                script = self._wsl_toolchain() + "cd -- \"$1\"; gradle wrapper --gradle-version " + self.GRADLE_VERSION
                rc, out, err = run_command(script, args=[wsl_dir], timeout=900)
                if rc == 0 and unix.exists():
                    self.log("[gradle] wrapper generated through WSL")
                    return unix
                self.log(f"[gradle] WSL wrapper bootstrap failed: {err or out}")
            except Exception as exc:
                self.log(f"[gradle] WSL wrapper bootstrap skipped: {exc}")
        return None

    def _build_wsl(self, artifact: str) -> dict:
        from part1_builder.wsl_connector import run_command
        wsl_dir = self._wsl_dir()
        tasks = []
        if artifact in {"apk", "both"}: tasks.append(("apk", "assembleRelease"))
        if artifact in {"aab", "both"}: tasks.append(("aab", "bundleRelease"))
        if not tasks:
            raise ValueError(f"Unsupported artifact: {artifact}")
        gradle_root = f"$HOME/.juprisx/tools/gradle-{self.GRADLE_VERSION}"
        env_setup = self._wsl_toolchain() + f"cd -- \"$1\"; if [ ! -x ./gradlew ]; then gradle wrapper --gradle-version {self.GRADLE_VERSION}; fi; "
        outputs = {}
        for kind, task in tasks:
            self.log(f"[WSL/gradle] {task}")
            rc, out, err = run_command(env_setup + f"./gradlew {task}", args=[wsl_dir], timeout=1800)
            if rc != 0:
                raise RuntimeError(f"WSL Gradle {task} failed:\n{out[-4000:]}\n{err[-4000:]}")
            ext = "apk" if kind == "apk" else "aab"
            found = sorted(self.android_dir.rglob(f"*.{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not found:
                raise RuntimeError(f"Gradle completed but no .{ext} artifact was produced.")
            outputs[kind] = str(found[0])
            self.log(f"[gradle] {kind.upper()}: {found[0]}")
        return outputs

    def build(self, artifact: str = "both") -> dict:
        android = self.android_dir
        if not (android / "settings.gradle").exists() and not (android / "settings.gradle.kts").exists():
            raise FileNotFoundError("Native Android template is missing: android/settings.gradle")
        java_home = self._java_home()
        sdk = self._android_sdk()
        wrapper = self._ensure_wrapper()
        if not java_home or not sdk or not wrapper:
            if os.name == "nt":
                self.log("[build] Windows toolchain incomplete; falling back to WSL Android toolchain")
                return self._build_wsl(artifact)
            missing = []
            if not java_home: missing.append("JDK/keytool")
            if not sdk: missing.append("Android SDK")
            if not wrapper: missing.append("Gradle wrapper")
            raise FileNotFoundError("Missing Android toolchain: " + ", ".join(missing))

        commands = []
        if artifact in {"apk", "both"}: commands.append(("apk", "assembleRelease"))
        if artifact in {"aab", "both"}: commands.append(("aab", "bundleRelease"))
        if not commands: raise ValueError(f"Unsupported artifact: {artifact}")
        outputs = {}
        env = os.environ.copy()
        env["JAVA_HOME"] = java_home
        env["ANDROID_SDK_ROOT"] = sdk
        env["ANDROID_HOME"] = sdk
        env["PATH"] = str(Path(java_home) / "bin") + os.pathsep + env.get("PATH", "")
        for kind, task in commands:
            self.log(f"[gradle] {Path(str(wrapper)).name} {task}")
            proc = subprocess.run([str(wrapper), task], cwd=android, env=env, capture_output=True, text=True, shell=(os.name == "nt" and str(wrapper).endswith(".bat")))
            if proc.returncode != 0:
                raise RuntimeError(f"Gradle {task} failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}")
            ext = "apk" if kind == "apk" else "aab"
            found = sorted(android.rglob(f"*.{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not found: raise RuntimeError(f"Gradle completed but no .{ext} artifact was produced.")
            outputs[kind] = str(found[0]); self.log(f"[gradle] {kind.upper()}: {found[0]}")
        return outputs

    @staticmethod
    def ensure_wrapper(android_dir: str) -> bool:
        root = Path(android_dir)
        return (root / "gradlew.bat").exists() or (root / "gradlew").exists() or shutil.which("gradle") is not None
