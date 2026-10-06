from __future__ import annotations
from datetime import datetime
from pathlib import Path
import os, secrets, shutil, subprocess


def _find_keytool() -> str:
    exe = "keytool.exe" if os.name == "nt" else "keytool"
    candidates: list[Path] = []
    for env_name in ("JAVA_HOME", "JDK_HOME"):
        value = os.environ.get(env_name)
        if value:
            root = Path(value); candidates += [root / "bin" / exe, root / "jre" / "bin" / exe]
    found = shutil.which(exe) or shutil.which("keytool")
    if found: return str(Path(found).resolve())
    if os.name == "nt":
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")); pfx86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")); local = Path(os.environ.get("LOCALAPPDATA", ""))
        roots = [pf / "Android" / "Android Studio" / "jbr", local / "Programs" / "Android Studio" / "jbr", pf / "Java", pfx86 / "Java", pf / "Eclipse Adoptium", pf / "Microsoft", pf / "Amazon Corretto"]
        for root in roots:
            if root.exists(): candidates.extend(root.glob("**/bin/keytool.exe"))
        try:
            proc = subprocess.run(["where.exe", "keytool.exe"], capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    p = Path(line.strip())
                    if p.is_file(): return str(p.resolve())
        except OSError: pass
    else:
        for root in (Path("/usr/lib/jvm"), Path("/opt/java"), Path("/opt/android-studio/jbr")):
            if root.exists(): candidates.extend(root.glob("**/bin/keytool"))
    for candidate in candidates:
        if candidate.is_file(): return str(candidate.resolve())
    raise FileNotFoundError("Java keytool was not found. Install Android Studio/JDK or set JAVA_HOME/JDK_HOME.")


def generate_keystore(keystore_path: str, alias: str, store_pass: str | None = None, key_pass: str | None = None,
                      dname: str = "CN=JuprisX, OU=Agent, O=Jupris, L=Jakarta, ST=DKI, C=ID") -> dict:
    target = Path(keystore_path).expanduser().resolve()
    if target.exists(): raise FileExistsError(f"Keystore already exists, refusing to overwrite: {target}")
    store_pass = store_pass or os.environ.get("JX_KEYSTORE_PASSWORD") or secrets.token_urlsafe(24)
    key_pass = key_pass or os.environ.get("JX_KEY_PASSWORD") or store_pass
    if len(store_pass) < 6 or len(key_pass) < 6: raise ValueError("keytool requires passwords of at least 6 characters.")
    target.parent.mkdir(parents=True, exist_ok=True)
    keytool = _find_keytool(); env = {**os.environ, "JX_STORE_PASS": store_pass, "JX_KEY_PASS": key_pass}
    cmd = [keytool, "-genkeypair", "-v", "-keystore", str(target), "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000", "-alias", alias, "-storepass:env", "JX_STORE_PASS", "-keypass:env", "JX_KEY_PASS", "-dname", dname]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    except OSError as exc:
        raise RuntimeError(f"Cannot execute keytool at {keytool}: {exc}. Check JAVA_HOME/JDK installation.") from exc
    if proc.returncode != 0 or not target.exists():
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"Failed to generate keystore with {keytool}: {detail or 'keytool returned a failure'}")
    return {"path": str(target), "alias": alias, "store_password": store_pass, "key_password": key_pass, "generated_at": datetime.now().isoformat()}
