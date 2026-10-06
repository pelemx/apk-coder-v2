"""Legacy compatibility name for the native Windows Android toolchain checker.

HTML/JS projects do not use Buildozer, python-for-android, pygame, or WSL for
packaging. Existing GUI imports are kept temporarily so older project state does
not crash; all checks now resolve local JDK + Gradle instead.
"""
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
    raise RuntimeError("WSL execution is disabled for HTML/JS Android builds; use native Gradle.")


def stream_in_wsl(command: str, *args, **kwargs) -> int:
    raise RuntimeError("WSL execution is disabled for HTML/JS Android builds; use native Gradle.")


def to_wsl_path(path: str) -> str:
    return str(path)


def wsl_available() -> bool:
    return False


def _find_java_home() -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")).exists():
        return java_home
    java = shutil.which("java.exe" if os.name == "nt" else "java") or shutil.which("java")
    if java:
        return str(Path(java).resolve().parent.parent)
    if os.name == "nt":
        for root in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Android Studio" / "jbr",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "jbr",
        ):
            if (root / "bin" / "java.exe").exists():
                return str(root)
    return ""


def check_wsl_environment(distro: str | None = None) -> dict[str, Any]:
    """Compatibility API returning native Windows Gradle/JDK readiness."""
    root = Path.cwd()
    java_home = _find_java_home()
    keytool = bool(java_home) and (Path(java_home) / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")).exists()
    gradle_wrapper = any((root / p).exists() for p in ("android/gradlew.bat", "android/gradlew"))
    gradle = shutil.which("gradle") is not None
    return {
        "is_wsl": False,
        "mode": "windows-native" if host_is_windows() else "linux-native",
        "python_version": "",
        "pygame_installed": False,
        "cython_installed": False,
        "jdk_available": bool(java_home and keytool),
        "android_sdk": False,
        "buildozer_available": False,
        "gradle_available": gradle_wrapper or gradle,
        "java_home": java_home,
        "missing_apt": [],
        "ready": bool(java_home and keytool and (gradle_wrapper or gradle)),
        "errors": [] if (java_home and keytool and (gradle_wrapper or gradle)) else [
            x for x, ok in (
                ("JDK/keytool not found; install Android Studio/JDK or set JAVA_HOME.", bool(java_home and keytool)),
                ("Gradle wrapper missing; generated Android projects must contain android/gradlew.bat.", gradle_wrapper or gradle),
            ) if not ok
        ],
    }


def setup_commands(status: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def apply_setup(status: dict[str, Any] | None = None, distro: str | None = None,
                log=lambda line: None) -> dict[str, Any]:
    status = status or check_wsl_environment(distro)
    log("[setup] Native Android toolchain check (Windows/Gradle), no WSL/Buildozer")
    return status


_CACHE: dict[str, Any] = {"at": 0.0, "status": None}


def cached_check(ttl: float = 30.0, force: bool = False) -> dict[str, Any]:
    import time
    now = time.time()
    if force or _CACHE["status"] is None or now - _CACHE["at"] > ttl:
        _CACHE["status"] = check_wsl_environment()
        _CACHE["at"] = now
    return _CACHE["status"]


def invalidate_cache() -> None:
    _CACHE["status"], _CACHE["at"] = None, 0.0
