from __future__ import annotations

from datetime import datetime
from pathlib import Path


def generate_keystore(keystore_path: str, alias: str, store_pass: str, key_pass: str,
                      dname: str = "CN=JuprisX, OU=Agent, O=Jupris, L=Jakarta, ST=DKI, C=ID") -> dict:
    """Generate a release JKS using the local JDK. Never overwrite an existing key."""
    import os
    import subprocess

    target = Path(keystore_path).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Keystore already exists, refusing to overwrite: {target}")
    if len(store_pass) < 6 or len(key_pass) < 6:
        raise ValueError("keytool requires passwords of at least 6 characters.")
    target.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "JX_STORE_PASS": store_pass, "JX_KEY_PASS": key_pass}
    cmd = ["keytool", "-genkeypair", "-v", "-keystore", str(target), "-keyalg", "RSA",
           "-keysize", "2048", "-validity", "10000", "-alias", alias,
           "-storepass:env", "JX_STORE_PASS", "-keypass:env", "JX_KEY_PASS", "-dname", dname]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0 or not target.exists():
        raise RuntimeError(f"Failed to generate keystore: {(proc.stderr or proc.stdout).strip()}")
    return {"path": str(target), "alias": alias, "store_password": store_pass,
            "key_password": key_pass, "generated_at": datetime.now().isoformat()}
