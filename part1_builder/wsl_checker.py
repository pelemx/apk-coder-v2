"""WSL bridge + build-environment checker.

The desktop app runs on Windows; builds run inside WSL. Everything that touches the
build environment goes through run_in_wsl(), so the app, the validator and the agent
all agree on one definition of "the build environment".
"""
from __future__ import annotations

import os
import platform
import shlex
import subprocess
from typing import Any

# Apt packages Buildozer / python-for-android need on Ubuntu/Debian WSL distros.
APT_PACKAGES = [
    "build-essential", "git", "zip", "unzip", "openjdk-17-jdk", "python3-pip",
    "python3-venv", "autoconf", "automake", "libtool", "pkg-config", "cmake",
    "rsync", "zlib1g-dev", "libncurses-dev", "libffi-dev", "libssl-dev", "libltdl-dev",
]
VENV_DIR = "$HOME/.juprisx/venv"
BUILDOZER_BIN = f"{VENV_DIR}/bin/buildozer"
PIP_PACKAGES = ["buildozer", "cython==3.0.12", "virtualenv", "pygame"]


def host_is_windows() -> bool:
    return os.name == "nt"


def inside_wsl() -> bool:
    """True when THIS process runs inside WSL (not the normal case for the GUI)."""
    if platform.system() != "Linux":
        return False
    release = platform.uname().release.lower()
    return "microsoft" in release or "wsl" in release or "WSL_DISTRO_NAME" in os.environ


def _decode(data: bytes) -> str:
    # wsl.exe management commands (-l, --status) print UTF-16LE.
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
    """Run a bash command in the build environment. cwd is a Linux path (see to_wsl_path).

    extra_env values are passed through WSLENV on Windows, so secrets (keystore passwords)
    never appear on a command line.
    """
    if cwd:
        command = f"cd {shlex.quote(cwd)} && {command}"
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if host_is_windows():
        if extra_env:
            names = [n for n in extra_env]
            env["WSLENV"] = ":".join([env.get("WSLENV", "")] + names).strip(":")
        argv = _wsl_base(distro, as_root) + [command]
    else:
        argv = ["bash", "-lc", command]
    proc = subprocess.run(argv, capture_output=True, env=env, timeout=timeout)
    return subprocess.CompletedProcess(
        argv, proc.returncode, _decode(proc.stdout), _decode(proc.stderr))


def stream_in_wsl(command: str, on_line=lambda line: None, cwd: str | None = None,
                  extra_env: dict[str, str] | None = None, distro: str | None = None,
                  timeout: int | None = 7200) -> int:
    """Like run_in_wsl but forwards output line by line (long builds). Returns exit code."""
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
            on_line("[build] timed out, process killed")
            break
    return proc.wait()


def to_wsl_path(path: str) -> str:
    """C:\\Users\\me\\game -> /mnt/c/Users/me/game (no subprocess needed, deterministic)."""
    p = str(path)
    if not host_is_windows():
        return p
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    if p.startswith("//wsl.localhost/") or p.startswith("//wsl$/"):
        parts = p.split("/", 4)  # '', '', host, distro, rest
        return "/" + (parts[4] if len(parts) > 4 else "")
    return p


def wsl_available() -> bool:
    """Is a usable build environment reachable from this process?"""
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
    """Check the BUILD environment (WSL when the app runs on Windows)."""
    status: dict[str, Any] = {
        "is_wsl": False, "mode": "unavailable", "python_version": "",
        "pygame_installed": False, "jdk_available": False, "android_sdk": False,
        "buildozer_available": False, "missing_apt": [], "ready": False, "errors": [],
    }

    if host_is_windows() and not wsl_available():
        status["errors"].append(
            "WSL not found. Install it with 'wsl --install -d Ubuntu' (admin PowerShell), "
            "reboot, then reopen the app.")
        return status

    ok, kernel = _probe("uname -r", distro=distro)
    if not ok:
        status["errors"].append(f"Cannot run commands in the build environment: {kernel}")
        return status
    low = kernel.lower()
    status["is_wsl"] = "microsoft" in low or "wsl" in low
    status["mode"] = ("windows+wsl" if host_is_windows() else "wsl" if status["is_wsl"] else "linux")
    if not status["is_wsl"] and host_is_windows():
        status["errors"].append("The selected distro is not a WSL kernel.")

    ok, out = _probe("python3 --version", distro=distro)
    status["python_version"] = out.replace("Python", "").strip() if ok else ""
    if not ok:
        status["errors"].append("python3 missing in build environment.")

    status["pygame_installed"], _ = _probe(
        f"{VENV_DIR}/bin/python -c 'import pygame' || python3 -c 'import pygame'", distro=distro)
    status["cython_installed"], _ = _probe(
        f"{VENV_DIR}/bin/python -c 'import Cython' || python3 -c 'import Cython'", distro=distro)
    status["jdk_available"], _ = _probe("javac -version && keytool -help >/dev/null", distro=distro)
    if not status["jdk_available"]:
        status["errors"].append("JDK (javac/keytool) missing in build environment.")
    status["buildozer_available"], _ = _probe(
        f"test -x {BUILDOZER_BIN} || command -v buildozer", distro=distro)
    if not status["buildozer_available"]:
        status["errors"].append("Buildozer missing in build environment.")
    # SDK is downloaded by Buildozer on first build; report whether it already exists.
    status["android_sdk"], _ = _probe(
        'test -d "${ANDROID_HOME:-$HOME/.buildozer/android/platform/android-sdk}"', distro=distro)

    ok, out = _probe("dpkg -s " + " ".join(APT_PACKAGES) + " 2>&1 | grep -c 'install ok installed'",
                     distro=distro)
    if ok and out.isdigit() and int(out) < len(APT_PACKAGES):
        r = run_in_wsl("for p in " + " ".join(APT_PACKAGES) +
                       "; do dpkg -s $p >/dev/null 2>&1 || echo $p; done", distro=distro)
        status["missing_apt"] = r.stdout.split()

    # pygame is only needed for local testing, the APK is built from project sources.
    status["ready"] = bool(status["python_version"] and status["jdk_available"]
                           and status["buildozer_available"] and not status["missing_apt"]
                           and (status["is_wsl"] or status["mode"] == "linux"))
    return status


def setup_commands(status: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered, idempotent repair steps for whatever check_wsl_environment found missing.
    The agent/coder runs these (apt as root via wsl -u root, so no sudo password prompt)."""
    steps: list[dict[str, Any]] = []
    if status.get("missing_apt") or not status.get("jdk_available"):
        pkgs = " ".join(status.get("missing_apt") or APT_PACKAGES)
        steps.append({"name": "apt packages", "as_root": True, "timeout": 1800,
                      "command": f"apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y {pkgs}"})
    if not status.get("buildozer_available") or not status.get("pygame_installed") or not status.get("cython_installed"):
        steps.append({"name": "python venv (buildozer, cython, pygame)", "as_root": False, "timeout": 1800,
                      "command": f"(test -x {VENV_DIR}/bin/python || python3 -m venv {VENV_DIR}) && "
                                 f"export PIP_USER=false && " # <--- TAMBAHKAN INI
                                 f"{VENV_DIR}/bin/pip install --upgrade pip " + " ".join(PIP_PACKAGES)})
    return steps


def apply_setup(status: dict[str, Any] | None = None, distro: str | None = None,
                log=lambda line: None) -> dict[str, Any]:
    """Run the repair steps, then re-check. Returns the fresh status plus a step log."""
    status = status or check_wsl_environment(distro)
    results = []
    for step in setup_commands(status):
        log(f"[setup] {step['name']}...")
        try:
            r = run_in_wsl(step["command"], timeout=step["timeout"],
                           as_root=step["as_root"], distro=distro)
            results.append({"step": step["name"], "returncode": r.returncode,
                            "tail": (r.stdout + r.stderr)[-1500:]})
        except (OSError, subprocess.SubprocessError) as exc:
            results.append({"step": step["name"], "returncode": -1, "tail": str(exc)})
    invalidate_cache()
    fresh = check_wsl_environment(distro)
    fresh["setup_log"] = results
    return fresh


_CACHE: dict[str, Any] = {"at": 0.0, "status": None}


def cached_check(ttl: float = 30.0, force: bool = False) -> dict[str, Any]:
    """check_wsl_environment() spawns several wsl.exe processes; reuse a recent result."""
    import time
    now = time.time()
    if force or _CACHE["status"] is None or now - _CACHE["at"] > ttl:
        _CACHE["status"] = check_wsl_environment()
        _CACHE["at"] = now
    return _CACHE["status"]


def invalidate_cache() -> None:
    _CACHE["status"], _CACHE["at"] = None, 0.0
