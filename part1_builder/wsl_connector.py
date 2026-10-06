"""
WSL Connector Module
Menyediakan antarmuka aman untuk berinteraksi dengan WSL dari aplikasi Desktop Windows.

Penting: jangan membangun shell command dengan interpolasi path Windows. Path project
sering mengandung spasi, tanda kurung, &, dll. Gunakan run_script() dan positional
arguments agar Bash menerima path sebagai data, bukan syntax.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


def run_command(command: str, timeout: int = 60):
    """Menjalankan command Bash di WSL.

    Dipertahankan untuk command internal yang tidak menerima path dari user.
    Untuk path dinamis gunakan run_script().
    """
    try:
        result = subprocess.run(
            ["wsl.exe", "--", "bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def run_script(script: str, args: list[str] | None = None, timeout: int = 60):
    """Run a Bash script with arguments passed outside the shell source.

    ``bash -lc SCRIPT juprisx ARG...`` exposes ARGs as ``$1``, ``$2``, ... .
    This is the safe path for Windows/WSL project paths containing spaces or
    shell metacharacters such as ``(``, ``)``, ``&`` and ``;``.
    """
    args = [str(arg) for arg in (args or [])]
    try:
        result = subprocess.run(
            ["wsl.exe", "--", "bash", "-lc", script, "juprisx", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def windows_to_wsl_path(windows_path: str) -> str:
    """Convert a Windows drive path to /mnt/<drive>/... without shell quoting."""
    p = str(windows_path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    return p


def ensure_wsl_dir(wsl_path: str):
    """Memastikan direktori di WSL ada, aman untuk karakter khusus."""
    rc, _, _ = run_script("mkdir -p -- \"$1\"", [wsl_path])
    return rc == 0


def copy_file_to_wsl(windows_path: str, wsl_path: str) -> bool:
    """Menyalin file dari Windows ke WSL dengan path sebagai arguments."""
    if not os.path.exists(windows_path):
        return False
    src = windows_to_wsl_path(windows_path)
    rc, _, _ = run_script("mkdir -p -- \"$(dirname -- \"$2\")\" && cp -- \"$1\" \"$2\"", [src, wsl_path])
    return rc == 0


def copy_file_from_wsl(wsl_path: str, windows_path: str) -> bool:
    """Menyalin file dari WSL ke Windows dengan path sebagai arguments."""
    parent = os.path.dirname(windows_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    dest = windows_to_wsl_path(windows_path)
    rc, _, _ = run_script("cp -- \"$1\" \"$2\"", [wsl_path, dest])
    return rc == 0


def get_safe_keystore_path(windows_keystore_path: str) -> str:
    """Salin keystore ke folder Linux dan kembalikan path Linux absolut."""
    if not windows_keystore_path or windows_keystore_path.startswith("/"):
        return windows_keystore_path
    if not os.path.exists(windows_keystore_path):
        return windows_keystore_path

    rc, home, _ = run_command("printf '%s' \"$HOME\"")
    if rc != 0 or not home.startswith("/"):
        return windows_keystore_path

    safe = f"{home}/.juprisx/keystores/{os.path.basename(windows_keystore_path)}"
    if not ensure_wsl_dir(f"{home}/.juprisx/keystores"):
        return windows_keystore_path
    return safe if copy_file_to_wsl(windows_keystore_path, safe) else windows_keystore_path


def copy_build_artifacts_to_project(wsl_artifact_path: str, windows_project_dir: str, log=lambda line: None) -> str:
    """Menyalin APK/AAB dari WSL ke result_build di project Windows."""
    if not wsl_artifact_path:
        return ""
    filename = os.path.basename(wsl_artifact_path)
    result_dir = os.path.join(windows_project_dir, "result_build")
    dest_path = os.path.join(result_dir, filename)
    log(f"[WSL Connector] Menyalin {filename} ke folder result_build...")
    if copy_file_from_wsl(wsl_artifact_path, dest_path):
        log(f"[WSL Connector] Berhasil disalin ke: {dest_path}")
        return dest_path
    log(f"[WSL Connector] Gagal menyalin {filename}.")
    return ""
