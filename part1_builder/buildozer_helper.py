from __future__ import annotations
import os
import re
import shlex
import shutil
from pathlib import Path

from .wsl_checker import BUILDOZER_BIN, run_in_wsl, stream_in_wsl, to_wsl_path

SYNC_EXCLUDES = [".buildozer", "bin", ".juprisx", ".git", "__pycache__", ".venv", "venv"]


def _slug(project_dir: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(project_dir).name) or "project"



def _verify_release_artifact(path: Path, kind: str, log=lambda line: None) -> None:
    """Fail fast on the two causes that commonly look like an 'invalid package'.

    AAB files are upload artifacts and are NOT directly installable on Android.
    APKs are installable test artifacts and must be zip-aligned and signed.
    """
    if not path.is_file() or path.stat().st_size < 4096:
        raise RuntimeError(f"Invalid {kind}: artifact is missing or unexpectedly small: {path}")

    if kind == "apk":
        # Prefer Android build-tools from the SDK, falling back to PATH.
        apksigner = '$(find "${ANDROID_HOME:-$HOME/.buildozer/android/platform/android-sdk}/build-tools" -type f -name apksigner | sort -V | tail -1)'
        zipalign = '$(find "${ANDROID_HOME:-$HOME/.buildozer/android/platform/android-sdk}/build-tools" -type f -name zipalign | sort -V | tail -1)'
        apk = shlex.quote(to_wsl_path(str(path)))
        check = run_in_wsl(
            f'test -x {apksigner} && {apksigner} verify --verbose {apk} '
            f'&& test -x {zipalign} && {zipalign} -c -P 16 -v 4 {apk}',
            timeout=120,
        )
        if check.returncode != 0:
            raise RuntimeError(
                f"Release APK failed signature/16-KB alignment validation: "
                f"{(check.stdout + check.stderr)[-1600:]}"
            )
        log("[build] APK signature + 16 KB zip alignment: OK")
    elif kind == "aab":
        aab = shlex.quote(to_wsl_path(str(path)))
        check = run_in_wsl(
            f'jarsigner -verify -strict -verbose {aab}',
            timeout=120,
        )
        if check.returncode != 0:
            raise RuntimeError(
                f"Release AAB failed JAR signature validation: "
                f"{(check.stdout + check.stderr)[-1600:]}"
            )
        log("[build] AAB signature: OK")
        log("[build] AAB is for Google Play upload; do not try to install the .aab directly.")

def run_buildozer_release(project_dir: str, keystore_info: dict,
                          artifacts: tuple[str, ...] = ("aab", "apk"),
                          log=lambda line: None) -> dict:
    """Build and sign release artifacts inside WSL and copy them to <project>/bin.

    The project is synced into the Linux filesystem first: building on /mnt/c is very slow and
    breaks on file permissions. .buildozer (SDK/NDK cache) stays on the Linux side between builds.
    """
    src = to_wsl_path(project_dir)
    build_dir = f"$HOME/.juprisx/build/{_slug(project_dir)}"
    excludes = " ".join(f"--exclude={shlex.quote(e)}" for e in SYNC_EXCLUDES)

    src_q = shlex.quote(src.rstrip("/") + "/")
    tar_excludes = " ".join(f"--exclude={shlex.quote('./' + e)}" for e in SYNC_EXCLUDES)
    sync_cmd = (
        f'mkdir -p "{build_dir}" && if command -v rsync >/dev/null 2>&1; then '
        f'rsync -a --delete {excludes} {src_q} "{build_dir}/"; '
        f'else (cd {src_q} && tar {tar_excludes} -cf - .) | (cd "{build_dir}" && tar -xf -); fi'
    )
    r = run_in_wsl(sync_cmd, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"Could not sync project into build environment: {(r.stderr or r.stdout)[-800:]}")
    app_root = Path(__file__).resolve().parent.parent
    recipes_src = to_wsl_path(str(app_root / "p4a-recipes"))
    run_in_wsl(f'cp -rf {shlex.quote(recipes_src)} "{build_dir}/"')


    # Signing material is passed via environment (WSLENV on Windows), never on a command line.
    env = {
        "P4A_RELEASE_KEYSTORE": to_wsl_path(keystore_info["path"]),
        "P4A_RELEASE_KEYALIAS": keystore_info["alias"],
        "P4A_RELEASE_KEYSTORE_PASSWD": keystore_info["store_password"],
        "P4A_RELEASE_KEYALIAS_PASSWD": keystore_info["key_password"],
        "JAVA_HOME": "/usr/lib/jvm/java-1.17.0-openjdk-amd64",
        "PATH": "/usr/lib/jvm/java-1.17.0-openjdk-amd64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PIP_USER": "false"
    }
    bz = f'"$(test -x {BUILDOZER_BIN} && echo {BUILDOZER_BIN} || command -v buildozer)"'

    outputs: dict[str, str] = {}
    for kind in artifacts:
        log(f"[build] android release ({kind})")
        # release_artifact decides apk vs aab; set it in the Linux-side copy only.
        run_in_wsl(f"cd \"{build_dir}\" && sed -i -E 's/^#?[[:space:]]*android\\.release_artifact[[:space:]]*=.*/"
                       f"android.release_artifact = {kind}/' buildozer.spec", timeout=60)
        code = stream_in_wsl(f'cd "{build_dir}" && {bz} -v android release', on_line=log, extra_env=env)
        if code != 0:
            raise RuntimeError(f"buildozer failed for {kind} (exit {code}). See build log.")

        r = run_in_wsl(f'ls -t "{build_dir}"/bin/*.{kind} 2>/dev/null | head -1', timeout=60)
        produced = r.stdout.strip()
        if not produced:
            raise RuntimeError(f"Build finished but no .{kind} found in bin/.")
        dest_dir = Path(project_dir) / "bin"
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = produced.rsplit("/", 1)[-1]
        r = run_in_wsl(f'cp -f "{produced}" {shlex.quote(to_wsl_path(str(dest_dir / name)))}', timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"Could not copy {name} to the project: {r.stderr[-400:]}")
        output_path = dest_dir / name
        _verify_release_artifact(output_path, kind, log=log)
        outputs[kind] = str(output_path)
    return outputs
