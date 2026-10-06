from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path


class KeystoreManager:
    """Create or reuse a project-bound release signing identity."""

    def __init__(self, project_path: str):
        self.root = Path(project_path).expanduser().resolve()
        self.signing_dir = self.root / "signing"
        self.keystore = self.signing_dir / f"{self.root.name}.jks"
        self.properties = self.signing_dir / "signing.properties"

    def ensure(self, alias: str | None = None, password: str | None = None) -> dict:
        alias = alias or self._slug(self.root.name)
        password = password or os.environ.get("JX_KEYSTORE_PASSWORD") or secrets.token_urlsafe(24)
        self.signing_dir.mkdir(parents=True, exist_ok=True)
        if not self.keystore.exists():
            cmd = [
                "keytool", "-genkeypair", "-v",
                "-keystore", str(self.keystore),
                "-alias", alias,
                "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                "-storepass", password, "-keypass", password,
                "-dname", "CN=JuprisX, OU=Apps, O=JuprisX, C=ID",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0 or not self.keystore.exists():
                raise RuntimeError((proc.stderr or proc.stdout).strip() or "keytool failed")
        self.properties.write_text(
            f"storeFile={self.keystore.as_posix()}\n"
            f"storePassword={password}\n"
            f"keyAlias={alias}\n"
            f"keyPassword={password}\n",
            encoding="utf-8",
        )
        return {
            "path": str(self.keystore),
            "alias": alias,
            "store_password": password,
            "key_password": password,
            "properties": str(self.properties),
        }

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "app"
