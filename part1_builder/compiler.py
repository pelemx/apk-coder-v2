from __future__ import annotations
import os
import re
from pathlib import Path

from .buildozer_helper import run_buildozer_release
from .target_policy import load_policy

SPEC_NAME = "buildozer.spec"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower()) or "game"


def set_spec_values(text: str, values: dict[str, str], section: str = "app") -> str:
    """Set keys inside [section] of a buildozer.spec, preserving everything else.
    Replaces an active line, else un-comments a commented default, else appends."""
    lines = text.splitlines()
    header = f"[{section}]"
    start = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if start is None:
        lines += ["", header]
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))

    for key, value in values.items():
        active = re.compile(rf"^\s*{re.escape(key)}\s*=")
        commented = re.compile(rf"^\s*#\s*{re.escape(key)}\s*=")
        idx = next((i for i in range(start + 1, end) if active.match(lines[i])), None)
        if idx is None:
            idx = next((i for i in range(start + 1, end) if commented.match(lines[i])), None)
        if idx is None:
            lines.insert(end, f"{key} = {value}")
            end += 1
        else:
            lines[idx] = f"{key} = {value}"
    return "\n".join(lines) + "\n"


class CompilerPipeline:
    def __init__(self, project_dir: str, keystore_info: dict, log=lambda line: None):
        self.project_dir = project_dir
        self.keystore_info = keystore_info
        self.log = log

    def prepare_buildozer_spec(self) -> dict:
        """Create/patch buildozer.spec so the build is Play Store ready for the current policy."""
        policy = load_policy()
        root = Path(self.project_dir)
        spec = root / SPEC_NAME
        created = not spec.exists()
        text = spec.read_text(encoding="utf-8") if not created else "[app]\n"
        if created:
            title = root.name.replace("_", " ").replace("-", " ").title()
            text = set_spec_values(text, {
                "title": title,
                "package.name": _slug(root.name),
                "package.domain": "org.juprisx",
                "source.dir": ".",
                "source.include_exts": "py,png,jpg,jpeg,gif,webp,ttf,otf,wav,ogg,mp3,json,txt,atlas",
                "version": "0.1.0",
                "requirements": f"python3=={policy.get('python_version', '3.11')},pygame=={policy['pygame_version']}",
                "orientation": "portrait",
                "fullscreen": "1",
            })
            text = set_spec_values(text, {"log_level": "2", "warn_on_root": "1"}, section="buildozer")

        enforced = {
            "android.api": str(policy["target_api"]),
            "android.minapi": str(policy["min_api"]),
            "android.archs": ", ".join(policy["archs"]),
            "android.accept_sdk_license": "True",
            "android.release_artifact": policy.get("artifact", "aab"),
            "requirements": f"hostpython3=={policy.get('python_version', '3.11.9')},python3=={policy.get('python_version', '3.11.9')},pygame=={policy['pygame_version']}",
            "p4a.local_recipes": f"/home/{os.environ.get('LOGNAME', 'saharx')}/.juprisx/build/{_slug(root.name)}/p4a-recipes",
            "android.ndk_api": str(policy["min_api"]),
            "p4a.env_vars": "CFLAGS=-mfpu=neon -mfloat-abi=softfp"
        }
        # Never build a source tree that leaks our own metadata/build output into the package.
        excludes = "bin, .buildozer, .juprisx, .git, __pycache__"
        enforced["source.exclude_dirs"] = excludes
        if policy.get("p4a_branch"):
            enforced["p4a.branch"] = policy["p4a_branch"]
        if policy.get("ndk_version"):
            # Buildozer expects the NDK token WITHOUT the leading `r`.
            # Passing `r28c` makes it construct the invalid URL
            # `android-ndk-rr28c-linux.zip` (HTTP 404).
            ndk = str(policy["ndk_version"]).strip()
            if ndk.lower().startswith("r"):
                ndk = ndk[1:]
            enforced["android.ndk"] = ndk

        text = set_spec_values(text, enforced)
        spec.write_text(text, encoding="utf-8")
        return {"spec": str(spec), "created": created, "target_api": policy["target_api"],
                "min_api": policy["min_api"], "archs": policy["archs"]}

    def run_compile(self) -> dict:
        from .wsl_checker import check_wsl_environment
        env = check_wsl_environment()
        if not env["ready"]:
            return {"status": "error",
                    "message": "Build environment not ready: " + "; ".join(env["errors"] or ["see environment check"]),
                    "environment": env}
        try:
            spec_info = self.prepare_buildozer_spec()
            outputs = run_buildozer_release(self.project_dir, self.keystore_info, log=self.log)
            return {"status": "success", "apk": outputs.get("apk"), "aab": outputs.get("aab"),
                    "keystore": self.keystore_info["path"], "spec": spec_info}
        except Exception as exc:  # noqa: BLE001 - surfaced to the GUI/agent
            return {"status": "error", "message": str(exc)}
