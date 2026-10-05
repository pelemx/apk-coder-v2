from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .wsl_checker import host_is_windows, run_in_wsl, to_wsl_path

DEFAULT_DNAME = "CN=JuprisX, OU=Agent, O=Jupris, L=Jakarta, ST=DKI, C=ID"


def generate_keystore(keystore_path: str, alias: str, store_pass: str, key_pass: str,
                      dname: str = DEFAULT_DNAME) -> dict:
    """Generate a release keystore. Returns metadata for project.json.

    Never overwrites an existing keystore: losing/replacing the key makes Play Store
    updates impossible. Passwords go through env vars, not the command line.
    """
    target = Path(keystore_path)
    if target.exists():
        raise FileExistsError(f"Keystore already exists, refusing to overwrite: {target}")
    if len(store_pass) < 6 or len(key_pass) < 6:
        raise ValueError("keytool requires passwords of at least 6 characters.")
    target.parent.mkdir(parents=True, exist_ok=True)

    env_vars = {"JX_STORE_PASS": store_pass, "JX_KEY_PASS": key_pass}
    base = ("keytool -genkeypair -v -keyalg RSA -keysize 2048 -validity 10000 "
            "-storepass:env JX_STORE_PASS -keypass:env JX_KEY_PASS")

    if shutil.which("keytool"):
        cmd = ["keytool", "-genkeypair", "-v", "-keystore", str(target), "-keyalg", "RSA",
               "-keysize", "2048", "-validity", "10000", "-alias", alias,
               "-storepass:env", "JX_STORE_PASS", "-keypass:env", "JX_KEY_PASS",
               "-dname", dname]
        proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **env_vars})
    else:
        # No JDK on the Windows host: use the one in the build environment.
        import shlex
        command = (f"{base} -keystore {shlex.quote(to_wsl_path(str(target)))} "
                   f"-alias {shlex.quote(alias)} -dname {shlex.quote(dname)}")
        proc = run_in_wsl(command, extra_env=env_vars)

    if proc.returncode != 0 or not target.exists():
        raise RuntimeError(f"Failed to generate keystore: {(proc.stderr or proc.stdout).strip()}")

    return {
        "path": str(target),
        "alias": alias,
        "store_password": store_pass,  # project_manager is responsible for encrypting at rest
        "key_password": key_pass,
        "generated_at": datetime.now().isoformat(),
    }
