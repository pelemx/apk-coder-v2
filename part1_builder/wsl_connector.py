"""
WSL Connector Module
Menyediakan antarmuka bersih untuk berinteraksi dengan WSL dari aplikasi Desktop Windows.
"""
import subprocess
import os
import shlex
from pathlib import Path

def run_command(command: str, timeout: int = 60):
    """Menjalankan perintah bash di dalam WSL."""
    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def ensure_wsl_dir(wsl_path: str):
    """Memastikan direktori di WSL ada."""
    run_command(f"mkdir -p {shlex.quote(wsl_path)}")

def copy_file_to_wsl(windows_path: str, wsl_path: str) -> bool:
    """Menyalin file dari Windows ke WSL dengan aman."""
    if not os.path.exists(windows_path):
        return False
    
    p = windows_path.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        src = f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    else:
        src = p
        
    run_command(f"mkdir -p {shlex.quote(os.path.dirname(wsl_path))}")
    rc, _, _ = run_command(f"cp {shlex.quote(src)} {shlex.quote(wsl_path)}")
    return rc == 0

def copy_file_from_wsl(wsl_path: str, windows_path: str) -> bool:
    """Menyalin file dari WSL ke Windows dengan aman."""
    p = windows_path.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        dest = f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    else:
        dest = p
        
    os.makedirs(os.path.dirname(windows_path), exist_ok=True)
    rc, _, _ = run_command(f"cp {shlex.quote(wsl_path)} {shlex.quote(dest)}")
    return rc == 0

def get_safe_keystore_path(windows_keystore_path: str) -> str:
    """
    Salin keystore ke folder Linux dan kembalikan path ABSOLUT Linux.
    Mencegah error path ganda (/mnt/d/mnt/d/...) dan error permission Java.
    """
    if not windows_keystore_path or windows_keystore_path.startswith("/"):
        return windows_keystore_path
    if not os.path.exists(windows_keystore_path):
        return windows_keystore_path
        
    # Dapatkan path HOME absolut dari WSL
    rc, home, _ = run_command("echo $HOME")
    if rc != 0 or not home.startswith("/"):
        return windows_keystore_path
        
    safe = f"{home}/.juprisx/keystores/{os.path.basename(windows_keystore_path)}"
    
    # Buat folder dan salin
    ensure_wsl_dir(f"{home}/.juprisx/keystores")
    
    if copy_file_to_wsl(windows_keystore_path, safe):
        return safe # Berhasil, gunakan path Linux absolut
        
    # Fallback jika gagal copy
    return windows_keystore_path

def copy_build_artifacts_to_project(wsl_artifact_path: str, windows_project_dir: str, log=lambda line: None) -> str:
    """Menyalin hasil build (APK/AAB) dari WSL ke folder 'result_build' di dalam project Windows."""
    if not wsl_artifact_path:
        return ""
        
    filename = os.path.basename(wsl_artifact_path)
    result_dir = os.path.join(windows_project_dir, "result_build")
    dest_path = os.path.join(result_dir, filename)
    
    log(f"[WSL Connector] Menyalin {filename} ke folder result_build...")
    
    if copy_file_from_wsl(wsl_path=wsl_artifact_path, windows_path=dest_path):
        log(f"[WSL Connector] ✅ Berhasil disalin ke: {dest_path}")
        return dest_path
    else:
        log(f"[WSL Connector] ❌ Gagal menyalin {filename}.")
        return ""