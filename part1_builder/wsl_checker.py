"""Native Android toolchain checker kept under the legacy module name."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

BUILDOZER_BIN = ""
VENV_DIR = ""
PIP_PACKAGES: list[str] = []


def host_is_windows() -> bool:
    return os.name == "nt"


def inside_wsl() -> bool:
    return False


def run_in_wsl(command: str, *args, **kwargs):
    if os.name != "nt":
        return subprocess.run(["bash", "-lc", command], capture_output=True, text=True, **kwargs)
    return subprocess.run(["wsl.exe", "bash", "-lc", command], capture_output=True, text=True, **kwargs)


def stream_in_wsl(command: str, *args, **kwargs) -> int:
    proc = run_in_wsl(command, *args, **kwargs)
    return proc.returncode


def to_wsl_path(path: str) -> str:
    p = str(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    return p


def wsl_available() -> bool:
    if os.name != "nt":
        return False
    try:
        return subprocess.run(["wsl.exe", "--status"], capture_output=True, text=True, timeout=8).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _find_keytool() -> str:
    exe = "keytool.exe" if os.name == "nt" else "keytool"
    for env_name in ("JAVA_HOME", "JDK_HOME"):
        value = os.environ.get(env_name)
        if value:
            for p in (Path(value) / "bin" / exe, Path(value) / "jre" / "bin" / exe):
                if p.is_file():
                    return str(p.resolve())
    found = shutil.which(exe) or shutil.which("keytool")
    if found:
        return str(Path(found).resolve())
    if os.name == "nt":
        roots = [
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Android" / "Android Studio" / "jbr",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "jbr",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Java",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")) / "Java",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Eclipse Adoptium",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Microsoft",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Amazon Corretto",
        ]
        for root in roots:
            if root.exists():
                for p in root.glob("**/bin/keytool.exe"):
                    if p.is_file():
                        return str(p.resolve())
    return ""


def _find_java_home() -> str:
    kt = _find_keytool()
    if kt:
        return str(Path(kt).parent.parent.resolve())
    java_home = os.environ.get("JAVA_HOME") or os.environ.get("JDK_HOME")
    if java_home and (Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")).exists():
        return str(Path(java_home).resolve())
    java = shutil.which("java.exe" if os.name == "nt" else "java") or shutil.which("java")
    if java:
        return str(Path(java).resolve().parent.parent)
    return ""


def _find_android_sdk() -> str:
    candidates = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    if os.name == "nt":
        candidates += [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"),
            str(Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Android" / "Sdk"),
        ]
    else:
        candidates += [str(Path.home() / "Android" / "Sdk"), str(Path.home() / ".android" / "sdk")]
    for value in candidates:
        if value and (Path(value) / "platform-tools").exists():
            return str(Path(value).resolve())
    return ""


def _wsl_has(command: str) -> bool:
    if not wsl_available():
        return False
    try:
        proc = run_in_wsl(f"command -v {command}", timeout=8)
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:
        return False


def check_wsl_environment(distro: str | None = None) -> dict[str, Any]:
    java_home = _find_java_home()
    keytool = bool(_find_keytool())
    sdk = _find_android_sdk()
    gradle_windows = bool(shutil.which("gradle"))
    # The check is global, so a project-specific android/gradlew is not required here.
    # GradleBuilder creates android/ from the WebView template before build and can
    # bootstrap its wrapper from an installed Windows or WSL Gradle.
    gradle_wsl = _wsl_has("gradle")
    gradle = gradle_windows or gradle_wsl
    errors: list[str] = []
    if not java_home or not keytool:
        errors.append("JDK/keytool not found; install Android Studio/JDK or set JAVA_HOME.")
    if not sdk:
        errors.append("Android SDK not found; set ANDROID_SDK_ROOT/ANDROID_HOME or install the Android SDK.")
    if not gradle:
        errors.append("Gradle not found; install Gradle in Windows or WSL.")
    ready = bool(java_home and keytool and sdk and gradle)
    return {
        "is_wsl": False,
        "mode": "windows-native" if host_is_windows() else "linux-native",
        "python_version": "",
        "pygame_installed": False,
        "cython_installed": False,
        "jdk_available": bool(java_home and keytool),
        "android_sdk": bool(sdk),
        "android_sdk_path": sdk,
        "buildozer_available": False,
        "gradle_available": gradle,
        "java_home": java_home,
        "missing_apt": [],
        "ready": ready,
        "errors": errors,
        "bootstrap_wrapper": not bool(gradle_windows) and gradle_wsl,
    }


def setup_commands(status: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def apply_setup(status: dict[str, Any] | None = None, distro: str | None = None, log=lambda line: None) -> dict[str, Any]:
    status = status or check_wsl_environment(distro)
    log("[setup] Native Android toolchain check (Windows/Gradle)")
    return status


_CACHE = {"at": 0.0, "status": None}


def cached_check(ttl: float = 30.0, force: bool = False) -> dict[str, Any]:
    import time
    now = time.time()
    if force or _CACHE["status"] is None or now - _CACHE["at"] > ttl:
        _CACHE["status"], _CACHE["at"] = check_wsl_environment(), now
    return _CACHE["status"]


def invalidate_cache() -> None:
    _CACHE["status"], _CACHE["at"] = None, 0.0
