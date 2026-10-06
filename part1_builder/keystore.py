from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import secrets
import shutil
import subprocess


def _find_keytool() -> str:
    """Resolve keytool on Windows/Linux without requiring a PATH entry."""
    candidates: list[Path] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / ("keytool.exe" if os.name == "nt" else "keytool"))

    for name in ("keytool.exe", "keytool"):
        found = shutil.which(name)
        if found:
            return found

    if os.name == "nt":
        candidates.extend([
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Java",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Android Studio" / "jbr",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "jbr",
        ])
        for root in candidates[-3:]:
            if root.exists():
                matches = list(root.glob("**/bin/keytool.exe"))
                if matches:
                    return str(sorted(matches)[-1])
    else:
        candidates.extend([Path("/usr/lib/jvm"), Path("/opt/java"), Path("/opt/android-studio/jbr")])
        for root in candidates:
            if root.exists():
                matches = list(root.glob("**/bin/keytool"))
                if matches:
                    return str(sorted(matches)[-1])

    raise FileNotFoundError(
        "Java keytool was not found. Install a JDK or Android Studio, or set JAVA_HOME."
    )


def generate_keystore(keystore_path: str, alias: str, store_pass: str | None = None,
                      key_pass: str | None = None,
                      dname: str = "CN=JuprisX, OU=Agent, O=Jupris, L=Jakarta, ST=DKI, C=ID") -> dict:
    """Generate a project-bound JKS using the local JDK; never overwrite an existing key."""
    target = Path(keystore_path).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Keystore already exists, refusing to overwrite: {target}")

    # Auto-signing mode: generate a strong random password and persist it only in the
    # project signing.properties consumed by Gradle. An explicit password still wins.
    store_pass = store_pass or os.environ.get("JX_KEYSTORE_PASSWORD") or secrets.token_urlsafe(24)
    key_pass = key_pass or os.environ.get("JX_KEY_PASSWORD") or store_pass
    if len(store_pass) < 6 or len(key_pass) < 6:
        raise ValueError("keytool requires passwords of at least 6 characters.")

    target.parent.mkdir(parents=True, exist_ok=True)
    keytool = _find_keytool()
    env = {**os.environ, "JX_STORE_PASS": store_pass, "JX_KEY_PASS": key_pass}
    cmd = [keytool, "-genkeypair", "-v", "-keystore", str(target), "-keyalg", "RSA",
           "-keysize", "2048", "-validity", "10000", "-alias", alias,
           "-storepass:env", "JX_STORE_PASS", "-keypass:env", "JX_KEY_PASS", "-dname", dname]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0 or not target.exists():
        raise RuntimeError(f"Failed to generate keystore with {keytool}: {(proc.stderr or proc.stdout).strip()}")
    return {"path": str(target), "alias": alias, "store_password": store_pass,
            "key_password": key_pass, "generated_at": datetime.now().isoformat()}
