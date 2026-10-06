from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path


class KeystoreManager:
    """Create/reuse a project-bound release signing identity on Windows or Linux."""

    def __init__(self, project_path: str):
        self.root = Path(project_path).expanduser().resolve()
        self.signing_dir = self.root / "signing"
        self.keystore = self.signing_dir / f"{self.root.name}.jks"
        self.properties = self.signing_dir / "signing.properties"

    @staticmethod
    def _find_keytool() -> str:
        """Locate keytool without requiring Buildozer or a separate Python toolchain."""
        candidates: list[Path] = []
        for env_name in ("JAVA_HOME", "JDK_HOME"):
            value = os.environ.get(env_name)
            if value:
                root = Path(value)
                candidates.extend([
                    root / "bin" / ("keytool.exe" if os.name == "nt" else "keytool"),
                    root / "jre" / "bin" / ("keytool.exe" if os.name == "nt" else "keytool"),
                ])

        if os.name == "nt":
            local = Path(os.environ.get("LOCALAPPDATA", ""))
            pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            pfx86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            candidates.extend([
                pf / "Android" / "Android Studio" / "jbr" / "bin" / "keytool.exe",
                pfx86 / "Android" / "Android Studio" / "jbr" / "bin" / "keytool.exe",
                local / "Programs" / "Android Studio" / "jbr" / "bin" / "keytool.exe",
                pf / "Java" / "jdk-17" / "bin" / "keytool.exe",
                pf / "Java" / "jdk-21" / "bin" / "keytool.exe",
                pfx86 / "Java" / "jdk-17" / "bin" / "keytool.exe",
                pfx86 / "Java" / "jdk-21" / "bin" / "keytool.exe",
            ])
            # Android Studio/JDK installations can use arbitrary version directories.
            for root in (pf / "Android" / "Android Studio", pf / "Java", pfx86 / "Java", local / "Programs" / "Android Studio"):
                if root.exists():
                    candidates.extend(root.glob("**/bin/keytool.exe"))
        else:
            for root in (Path("/usr/lib/jvm"), Path("/opt/java"), Path("/opt/android-studio/jbr")):
                if root.exists():
                    candidates.extend(root.glob("**/bin/keytool"))

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())

        for name in ("keytool.exe", "keytool"):
            found = shutil.which(name)
            if found:
                return found

        raise FileNotFoundError(
            "Java keytool was not found. Set JAVA_HOME/JDK_HOME or install a JDK/Android Studio."
        )

    def ensure(self, alias: str | None = None, password: str | None = None) -> dict:
        alias = alias or self._slug(self.root.name)
        self.signing_dir.mkdir(parents=True, exist_ok=True)
        if self.keystore.exists() and self.properties.exists():
            values = self._read_properties()
            values.setdefault("path", str(self.keystore))
            values.setdefault("alias", alias)
            return values

        password = password or os.environ.get("JX_KEYSTORE_PASSWORD") or secrets.token_urlsafe(24)
        key_password = os.environ.get("JX_KEY_PASSWORD") or password
        keytool = self._find_keytool()
        env = {**os.environ, "JX_STORE_PASS": password, "JX_KEY_PASS": key_password}
        cmd = [
            keytool, "-genkeypair", "-v",
            "-keystore", str(self.keystore),
            "-alias", alias,
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
            "-storepass:env", "JX_STORE_PASS",
            "-keypass:env", "JX_KEY_PASS",
            "-dname", "CN=JuprisX, OU=Apps, O=JuprisX, C=ID",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Unable to execute keytool: {keytool}") from exc
        if proc.returncode != 0 or not self.keystore.exists():
            raise RuntimeError((proc.stderr or proc.stdout).strip() or "keytool failed")

        self.properties.write_text(
            f"storeFile={self.keystore.resolve()}\nstorePassword={password}\n"
            f"keyAlias={alias}\nkeyPassword={key_password}\n",
            encoding="utf-8",
        )
        return {
            "path": str(self.keystore),
            "alias": alias,
            "store_password": password,
            "key_password": key_password,
            "properties": str(self.properties),
        }

    def _read_properties(self) -> dict:
        values = {}
        for line in self.properties.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return {
            "path": values.get("storeFile", str(self.keystore)),
            "alias": values.get("keyAlias", ""),
            "store_password": values.get("storePassword", ""),
            "key_password": values.get("keyPassword", ""),
            "properties": str(self.properties),
        }

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "app"
