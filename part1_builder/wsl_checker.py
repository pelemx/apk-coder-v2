"""WSL/Linux bridge and Android Gradle build-environment checker.

The desktop app may run on Windows while Android builds run in WSL/Linux. This
module contains only generic environment/command transport; it has no Pygame,
Buildozer, or python-for-android dependency.
"""
from __future__ import annotations

import os
import platform
import shlex
import subprocess
from typing import Any

APT_PACKAGES = [
    "build-essential", "git", "zip", "unzip", "openjdk-17-jdk", "python3-pip",
    "python3-venv", "curl", "wget", "unzip", "rsync",
]


def host_is_windows() -> bool:
    return os.name == "nt"


def inside_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    release = platform.uname().release.lower()
    return "microsoft" in release or "wsl" in release or "WSL_DISTRO_NAME" in os.environ


def _decode(data: bytes) -> str:
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="replace").replace("\x00", "")
    return data.decode("utf-8", errors="replace")


def _wsl_base(distro: str | None = None, as_root: bool = False) -> list[str]:
    cmd = ["wsl.exe"]
    if distro:
        cmd += ["-d", distro]
    if as_root:
        cmd += ["-u", "root"]
    return cmd + ["-e", "bash", "-lc"]


def run_in_wsl(command: str, cwd: str | None = None, timeout: int | None = 600,
               extra_env: dict[str, str] | None = None, as_root: bool = False,
               distro: str | None = None) -> subprocess.CompletedProcess:
    if cwd:
        command = f"cd {shlex.quote(cwd)} && {command}"
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if host_is_windows():
        if extra_env:
            env["WSLENV"] = ":".join([env.get("WSLENV", "")] + list(extra_env)).strip(":")
        argv = _wsl_base(distro, as_root) + [command]
    else:
        argv = ["bash", "-lc", command]
    proc = subprocess.run(argv, capture_output=True, env=env, timeout=timeout)
    return subprocess.CompletedProcess(argv, proc.returncode, _decode(proc.stdout), _decode(proc.stderr))


def stream_in_wsl(command: str, on_line=lambda line: None, cwd: str | None = None,
                  extra_env: dict[str, str] | None = None, distro: str | None = None,
                  timeout: int | None = 7200) -> int:
    import time
    if cwd:
        command = f"cd {shlex.quote(cwd)} && {command}"
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if host_is_windows():
        if extra_env:
            env["WSLENV"] = ":".join([env.get("WSLENV", "")] + list(extra_env)).strip(":")
        argv = _wsl_base(distro) + [command]
    else:
        argv = ["bash", "-lc", command]
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    start = time.time()
    assert proc.stdout is not None
    for raw in iter(proc.stdout.readline, b""):
        on_line(raw.decode("utf-8", errors="replace").rstrip())
        if timeout and time.time() - start > timeout:
            proc.kill()
            on_line("[gradle] timed out, process killed")
            break
    return proc.wait()


def to_wsl_path(path: str) -> str:
    p = str(path)
    if not host_is_windows():
        return p
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    if p.startswith("//wsl.localhost/") or p.startswith("//wsl$/"):
        parts = p.split("/", 4)
        return "/" + (parts[4] if len(parts) > 4 else "")
    return p


def wsl_available() -> bool:
    if not host_is_windows():
        return True
    try:
        out = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=20)
        return out.returncode == 0 and bool(_decode(out.stdout).strip())
    except (OSError, subprocess.SubprocessError):
        return False


def _probe(command: str, **kw) -> tuple[bool, str]:
    try:
        r = run_in_wsl(command, timeout=kw.pop("timeout", 60), **kw)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def check_wsl_environment(distro: str | None = None) -> dict[str, Any]:
    """Check JDK, Gradle and Android SDK availability for native WebView builds."""
    status: dict[str, Any] = {
        "is_wsl": False,
        "mode": "unavailable",
        "python_version": "",
        "jdk_available": False,
        "gradle_available": False,
        "android_sdk": False,
        "ready": False,
        "errors": [],
    }
    if host_is_windows() and not wsl_available():
        status["errors"].append("WSL is unavailable. Install/enable WSL and an Ubuntu distro.")
        return status

    ok, kernel = _probe("uname -r", distro=distro)
    if not ok:
        status["errors"].append(f"Cannot run commands in the build environment: {kernel}")
        return status
    low = kernel.lower()
    status["is_wsl"] = "microsoft" in low or "wsl" in low
    status["mode"] = "windows+wsl" if host_is_windows() else ("wsl" if status["is_wsl"] else "linux")

    ok, out = _probe("python3 --version", distro=distro)
    status["python_version"] = out.replace("Python", "").strip() if ok else ""

    status["jdk_available"], _ = _probe("javac -version && keytool -help >/dev/null", distro=distro)
    status["gradle_available"], _ = _probe("command -v gradle >/dev/null || test -x ./gradlew", distro=distro)
    status["android_sdk"], _ = _probe(
        'test -d "${ANDROID_HOME:-$ANDROID_SDK_ROOT}" || test -d "$HOME/Android/Sdk"', distro=distro)

    if not status["jdk_available"]:
        status["errors"].append("JDK 17 (javac/keytool) is missing.")
    if not status["gradle_available"]:
        status["errors"].append("Gradle is missing. A generated project may use its gradle wrapper when present.")
    if not status["android_sdk"]:
        status["errors"].append("Android SDK is not detected.")

    status["ready"] = bool(status["jdk_available"] and status["gradle_available"] and status["android_sdk"])
    return status


def setup_commands(status: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if not status.get("jdk_available"):
        steps.append({
            "name": "Android/JDK prerequisites", "as_root": True, "timeout": 1800,
            "command": "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y " + " ".join(APT_PACKAGES),
        })
    if not status.get("gradle_available"):
        steps.append({
            "name": "Gradle check", "as_root": False, "timeout": 120,
            "command": "command -v gradle >/dev/null || echo 'Gradle wrapper is expected inside the generated Android project.'",
        })
    return steps


def apply_setup(status: dict[str, Any] | None = None, distro: str | None = None,
                log=lambda line: None) -> dict[str, Any]:
    status = status or check_wsl_environment(distro)
    results = []
    for step in setup_commands(status):
        log(f"[setup] {step['name']}...")
        try:
            r = run_in_wsl(step["command"], timeout=step["timeout"], as_root=step["as_root"], distro=distro)
            results.append({"step": step["name"], "returncode": r.returncode, "tail": (r.stdout + r.stderr)[-1500:]})
        except (OSError, subprocess.SubprocessError) as exc:
            results.append({"step": step["name"], "returncode": -1, "tail": str(exc)})
    invalidate_cache()
    fresh = check_wsl_environment(distro)
    fresh["setup_log"] = results
    return fresh


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
