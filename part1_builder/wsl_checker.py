"""Native Android toolchain checker kept under the legacy module name for compatibility."""
from __future__ import annotations
import os, shutil
from pathlib import Path
from typing import Any

BUILDOZER_BIN = ""; VENV_DIR = ""; PIP_PACKAGES: list[str] = []

def host_is_windows() -> bool: return os.name == "nt"
def inside_wsl() -> bool: return False
def run_in_wsl(command: str, *args, **kwargs): raise RuntimeError("WSL execution is not used by the native Gradle HTML/JS builder.")
def stream_in_wsl(command: str, *args, **kwargs) -> int: raise RuntimeError("WSL execution is not used by the native Gradle HTML/JS builder.")
def to_wsl_path(path: str) -> str: return str(path)
def wsl_available() -> bool: return False


def _find_java_home() -> str:
    java_home = os.environ.get("JAVA_HOME") or os.environ.get("JDK_HOME")
    if java_home and (Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")).exists(): return java_home
    java = shutil.which("java.exe" if os.name == "nt" else "java") or shutil.which("java")
    if java: return str(Path(java).resolve().parent.parent)
    if os.name == "nt":
        for root in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Android Studio" / "jbr", Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "jbr"):
            if (root / "bin" / "java.exe").exists(): return str(root)
    return ""


def _find_android_sdk() -> str:
    candidates = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    if os.name == "nt":
        candidates += [str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"), str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Sdk")]
    else:
        candidates += [str(Path.home() / "Android" / "Sdk"), str(Path.home() / ".android" / "sdk")]
    for value in candidates:
        if value and (Path(value) / "platform-tools").exists(): return str(Path(value).resolve())
    return ""


def check_wsl_environment(distro: str | None = None) -> dict[str, Any]:
    root = Path.cwd(); java_home = _find_java_home(); sdk = _find_android_sdk()
    keytool = bool(java_home) and (Path(java_home) / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")).exists()
    gradle_wrapper = any((root / p).exists() for p in ("android/gradlew.bat", "android/gradlew")); gradle = shutil.which("gradle") is not None
    ready = bool(java_home and keytool and sdk and (gradle_wrapper or gradle))
    errors = []
    if not java_home or not keytool: errors.append("JDK/keytool not found; install Android Studio/JDK or set JAVA_HOME.")
    if not sdk: errors.append("Android SDK not found; set ANDROID_SDK_ROOT/ANDROID_HOME or install Android Studio SDK.")
    if not (gradle_wrapper or gradle): errors.append("Gradle wrapper missing; generated Android projects must contain android/gradlew.bat.")
    return {"is_wsl": False, "mode": "windows-native" if host_is_windows() else "linux-native", "python_version": "", "pygame_installed": False, "cython_installed": False, "jdk_available": bool(java_home and keytool), "android_sdk": bool(sdk), "android_sdk_path": sdk, "buildozer_available": False, "gradle_available": gradle_wrapper or gradle, "java_home": java_home, "missing_apt": [], "ready": ready, "errors": errors}


def setup_commands(status: dict[str, Any]) -> list[dict[str, Any]]: return []
def apply_setup(status: dict[str, Any] | None = None, distro: str | None = None, log=lambda line: None) -> dict[str, Any]:
    status = status or check_wsl_environment(distro); log("[setup] Native Android toolchain check (Windows/Gradle), no WSL/Buildozer"); return status
_CACHE = {"at": 0.0, "status": None}
def cached_check(ttl: float = 30.0, force: bool = False) -> dict[str, Any]:
    import time
    now = time.time()
    if force or _CACHE["status"] is None or now - _CACHE["at"] > ttl: _CACHE["status"], _CACHE["at"] = check_wsl_environment(), now
    return _CACHE["status"]
def invalidate_cache() -> None: _CACHE["status"], _CACHE["at"] = None, 0.0
