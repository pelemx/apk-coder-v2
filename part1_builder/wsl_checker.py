"""Native Android toolchain checker kept under the legacy module name."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

BUILDOZER_BIN = ""
VENV_DIR = ""
PIP_PACKAGES: list[str] = []


def host_is_windows() -> bool:
    return os.name == "nt"


def inside_wsl() -> bool:
    return False


def run_in_wsl(command: str, *args, **kwargs):
    if os.name != "nt":
        return subprocess.run(["bash", "-lc", command], capture_output=True, text=True, **kwargs)
    return subprocess.run(["wsl.exe", "bash", "-lc", command], capture_output=True, text=True, **kwargs)


def stream_in_wsl(command: str, *args, **kwargs) -> int:
    proc = run_in_wsl(command, *args, **kwargs)
    return proc.returncode


def to_wsl_path(path: str) -> str:
    p = str(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    return p


def wsl_available() -> bool:
    if os.name != "nt":
        return False
    try:
        return subprocess.run(["wsl.exe", "--status"], capture_output=True, text=True, timeout=8).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _find_keytool() -> str:
    exe = "keytool.exe" if os.name == "nt" else "keytool"
    for env_name in ("JAVA_HOME", "JDK_HOME"):
        value = os.environ.get(env_name)
        if value:
            for p in (Path(value) / "bin" / exe, Path(value) / "jre" / "bin" / exe):
                if p.is_file():
                    return str(p.resolve())
    found = shutil.which(exe) or shutil.which("keytool")
    if found:
        return str(Path(found).resolve())
    if os.name == "nt":
        roots = [
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Android" / "Android Studio" / "jbr",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "jbr",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Java",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")) / "Java",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Eclipse Adoptium",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Microsoft",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Amazon Corretto",
        ]
        for root in roots:
            if root.exists():
                for p in root.glob("**/bin/keytool.exe"):
                    if p.is_file():
                        return str(p.resolve())
    return ""


def _find_java_home() -> str:
    kt = _find_keytool()
    if kt:
        return str(Path(kt).parent.parent.resolve())
    java_home = os.environ.get("JAVA_HOME") or os.environ.get("JDK_HOME")
    if java_home and (Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")).exists():
        return str(Path(java_home).resolve())
    java = shutil.which("java.exe" if os.name == "nt" else "java") or shutil.which("java")
    if java:
        return str(Path(java).resolve().parent.parent)
    return ""


def _find_android_sdk() -> str:
    candidates = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    if os.name == "nt":
        candidates += [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"),
            str(Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Android" / "Sdk"),
        ]
    else:
        candidates += [str(Path.home() / "Android" / "Sdk"), str(Path.home() / ".android" / "sdk")]
    for value in candidates:
        if value and (Path(value) / "platform-tools").exists():
            return str(Path(value).resolve())
    return ""


def _wsl_has(command: str) -> bool:
    if not wsl_available():
        return False
    try:
        proc = run_in_wsl(f"command -v {command}", timeout=8)
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:
        return False


def _wsl_sdk_root() -> str:
    return "$HOME/.juprisx/tools/android-sdk"


def _wsl_has_bootstrapped_sdk() -> bool:
    """check_wsl_environment()/_find_android_sdk() only look at Windows-side
    ANDROID_SDK_ROOT/ANDROID_HOME and Windows install paths. When the build
    falls back to WSL gradle (Windows toolchain incomplete), there is no SDK
    on the WSL side either unless we install one here, which leaves gradle
    with no sdk.dir and failing with "SDK location not found". This probes
    the WSL-side SDK this module bootstraps, independent of the Windows
    detection above.
    """
    if not wsl_available():
        return False
    try:
        proc = run_in_wsl(f"test -x {_wsl_sdk_root()}/platform-tools/adb", timeout=8)
        return proc.returncode == 0
    except Exception:
        return False


def ensure_wsl_android_sdk(api: str = "34", build_tools: str = "34.0.0", log=lambda line: None) -> str:
    """Bootstrap a minimal Android SDK inside WSL (cmdline-tools, platform-tools,
    the requested platform and build-tools), accepting licenses non-interactively.
    Returns the WSL sdk root path on success, "" on failure. No-op (fast) if
    already present.
    """
    sdk_root = _wsl_sdk_root()
    if _wsl_has_bootstrapped_sdk():
        return sdk_root
    log("[setup] Bootstrapping Android SDK inside WSL (cmdline-tools + platform-tools + "
        f"platforms;android-{api} + build-tools;{build_tools}) ...")
    script = (
        f"set -e; SDK={sdk_root}; mkdir -p \"$SDK/cmdline-tools\"; "
        "if [ ! -x \"$SDK/cmdline-tools/latest/bin/sdkmanager\" ]; then "
        "curl -fsSL -o /tmp/juprisx-cmdline-tools.zip "
        "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip && "
        "unzip -oq /tmp/juprisx-cmdline-tools.zip -d \"$SDK/cmdline-tools\" && "
        "rm -rf \"$SDK/cmdline-tools/latest\" && "
        "mv \"$SDK/cmdline-tools/cmdline-tools\" \"$SDK/cmdline-tools/latest\"; fi; "
        "SDKMGR=\"$SDK/cmdline-tools/latest/bin/sdkmanager\"; "
        "yes | \"$SDKMGR\" --sdk_root=\"$SDK\" --licenses >/dev/null 2>&1 || true; "
        f"\"$SDKMGR\" --sdk_root=\"$SDK\" \"platform-tools\" \"platforms;android-{api}\" "
        f"\"build-tools;{build_tools}\" >/dev/null"
    )
    try:
        proc = run_in_wsl(script, timeout=900)
        if proc.returncode == 0 and _wsl_has_bootstrapped_sdk():
            log(f"[setup] WSL Android SDK ready at {sdk_root}")
            return sdk_root
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        log(f"[setup] WSL Android SDK bootstrap failed: {tail}")
        return ""
    except Exception as exc:
        log(f"[setup] WSL Android SDK bootstrap error: {exc}")
        return ""


def ensure_local_properties(project_dir_wsl: str, sdk_dir_wsl: str | None = None) -> bool:
    """Write/overwrite sdk.dir in <project_dir_wsl>/local.properties so WSL
    gradle can find the SDK. Call this right before every WSL gradle build
    that fell back from an incomplete Windows toolchain - a project's
    local.properties may already exist pointing at a (missing) Windows SDK
    path, which gradle will not auto-correct on its own.
    """
    sdk_dir_wsl = sdk_dir_wsl or _wsl_sdk_root()
    # sdk_dir_wsl is our own fixed "$HOME/..." template string - it must be
    # interpolated into the script text so bash expands $HOME, NOT passed as
    # a $2 positional (positional args are literal, never re-expanded, so
    # sdk.dir ended up as the literal text "$HOME/..." and silently relied
    # on ANDROID_HOME env fallback instead).
    script = (
        "mkdir -p -- \"$(dirname -- \"$1\")\" && "
        f"SDK_DIR=\"{sdk_dir_wsl}\"; "
        "{ grep -v '^sdk.dir=' \"$1\" 2>/dev/null; echo \"sdk.dir=$SDK_DIR\"; } > \"$1.tmp\" && "
        "mv \"$1.tmp\" \"$1\""
    )
    try:
        proc = subprocess.run(
            (["bash", "-lc", script, "juprisx", f"{project_dir_wsl}/local.properties"]
             if os.name != "nt" else
             ["wsl.exe", "bash", "-lc", script, "juprisx", f"{project_dir_wsl}/local.properties"]),
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _wsl_has_bootstrapped_gradle() -> bool:
    """Gradle installed by GradleBuilder._wsl_toolchain() lives under
    ~/.juprisx/tools and is only PATH-exported for the one-off build/setup
    subprocess, so plain `command -v gradle` (used by `_wsl_has`) never sees
    it on later calls. Check its actual install path directly so the
    environment check doesn't keep reporting "Gradle not found" after it
    has in fact been bootstrapped.
    """
    if not wsl_available():
        return False
    try:
        from core_engine.gradle_builder import GradleBuilder
        gradle_bin = f"$HOME/.juprisx/tools/gradle-{GradleBuilder.GRADLE_VERSION}/bin/gradle"
        proc = run_in_wsl(f"test -x {gradle_bin}", timeout=8)
        return proc.returncode == 0
    except Exception:
        return False


def check_wsl_environment(distro: str | None = None) -> dict[str, Any]:
    java_home = _find_java_home()
    keytool = bool(_find_keytool())
    sdk = _find_android_sdk()
    gradle_windows = bool(shutil.which("gradle"))
    # The check is global, so a project-specific android/gradlew is not required here.
    # GradleBuilder creates android/ from the WebView template before build and can
    # bootstrap its wrapper from an installed Windows or WSL Gradle.
    gradle_wsl = _wsl_has("gradle") or _wsl_has_bootstrapped_gradle()
    gradle = gradle_windows or gradle_wsl
    # SDK was only ever probed on the Windows side above. When the build is
    # going to run through WSL gradle anyway (gradle_windows is false), a WSL
    # SDK we bootstrapped ourselves is just as valid and must count here, or
    # "ready"/errors stay permanently wrong for a Windows+WSL-only setup.
    sdk_wsl = "" if sdk else (_wsl_sdk_root() if _wsl_has_bootstrapped_sdk() else "")
    sdk_effective = sdk or sdk_wsl
    errors: list[str] = []
    if not java_home or not keytool:
        errors.append("JDK/keytool not found; install Android Studio/JDK or set JAVA_HOME.")
    if not sdk_effective:
        errors.append("Android SDK not found; set ANDROID_SDK_ROOT/ANDROID_HOME or install the Android SDK.")
    if not gradle:
        errors.append("Gradle not found; install Gradle in Windows or WSL.")
    ready = bool(java_home and keytool and sdk_effective and gradle)
    return {
        "is_wsl": False,
        "mode": "windows-native" if host_is_windows() else "linux-native",
        "python_version": "",
        "pygame_installed": False,
        "cython_installed": False,
        "jdk_available": bool(java_home and keytool),
        "android_sdk": bool(sdk_effective),
        "android_sdk_path": sdk,
        "android_sdk_wsl_path": sdk_wsl,
        "buildozer_available": False,
        "gradle_available": gradle,
        "java_home": java_home,
        "missing_apt": [],
        "ready": ready,
        "errors": errors,
        "bootstrap_wrapper": not bool(gradle_windows) and gradle_wsl,
    }


def setup_commands(status: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def apply_setup(status: dict[str, Any] | None = None, distro: str | None = None, log=lambda line: None) -> dict[str, Any]:
    status = status or check_wsl_environment(distro)
    log("[setup] Native Android toolchain check (Windows/Gradle)")

    # Gradle/JDK missing on Windows but WSL present -> actually bootstrap the
    # WSL fallback toolchain here (Setup WSL button == explicit user fix
    # action), instead of only reporting "Gradle not found" with nothing the
    # user can do about it.
    if not status.get("gradle_available") and host_is_windows() and wsl_available():
        log("[setup] Gradle missing on Windows - bootstrapping JDK + Gradle inside WSL ...")
        try:
            from core_engine.gradle_builder import GradleBuilder
            script = GradleBuilder._wsl_toolchain() + "gradle -v"
            proc = run_in_wsl(script, timeout=900)
            if proc.returncode == 0:
                log("[setup] WSL Gradle bootstrap OK")
            else:
                tail = (proc.stderr or proc.stdout or "")[-2000:]
                log(f"[setup] WSL Gradle bootstrap failed: {tail}")
        except Exception as exc:
            log(f"[setup] WSL Gradle bootstrap error: {exc}")
        status = check_wsl_environment(distro)

    # Same gap for the SDK: _find_android_sdk() only ever looks on Windows,
    # so a Windows-incomplete / WSL-fallback setup never gets an SDK at all
    # unless we bootstrap one here too - this is what was missing before,
    # causing "SDK location not found" even after Setup WSL was run.
    if not status.get("android_sdk") and host_is_windows() and wsl_available():
        if ensure_wsl_android_sdk(log=log):
            status = check_wsl_environment(distro)

    return status


def prepare_wsl_build(project_dir_wsl: str, log=lambda line: None) -> bool:
    """Call this right before every WSL gradle invocation (assembleRelease/
    bundleRelease/etc). ensure_wsl_android_sdk()/ensure_local_properties()
    existed but nothing called them automatically, which is why sdk.dir had
    to be patched by hand each time. This is the single entry point the
    build pipeline (GradleBuilder) should call instead.
    """
    sdk_root = ensure_wsl_android_sdk(log=log)
    if not sdk_root:
        return False
    if not ensure_local_properties(project_dir_wsl, sdk_root):
        log("[setup] Failed to write local.properties")
        return False
    return True


_CACHE = {"at": 0.0, "status": None}


def cached_check(ttl: float = 30.0, force: bool = False) -> dict[str, Any]:
    import time
    now = time.time()
    if force or _CACHE["status"] is None or now - _CACHE["at"] > ttl:
        _CACHE["status"], _CACHE["at"] = check_wsl_environment(), now
    return _CACHE["status"]


def invalidate_cache() -> None:
    _CACHE["status"], _CACHE["at"] = None, 0.0