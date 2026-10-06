from __future__ import annotations
import os, re, shutil, subprocess
from pathlib import Path

class GradleBuilder:
    """Headless Gradle builder for the native Android WebView container."""
    def __init__(self, project_path: str, log=lambda line: None):
        self.root=Path(project_path).expanduser().resolve(); self.log=log
    @property
    def android(self): return self.root/"android"
    @property
    def gradle(self):
        wrapper=self.android/("gradlew.bat" if os.name=="nt" else "gradlew")
        return wrapper if wrapper.exists() else Path("gradle")
    def _run(self,task):
        if os.name=="nt" and not (self.android/"gradlew.bat").exists():
            p=str(self.android).replace("\\","/")
            if re.match(r"^[A-Za-z]:/",p): p=f"/mnt/{p[0].lower()}{p[2:]}"
            cmd=["wsl.exe","bash","-lc",f"cd {self._q(p)} && gradle {self._q(task)} --no-daemon"]
            return subprocess.run(cmd,capture_output=True,text=True)
        cmd=[str(self.gradle),task,"--no-daemon"]
        return subprocess.run(cmd,cwd=self.android,capture_output=True,text=True)
    @staticmethod
    def _q(value): return "'"+str(value).replace("'","'\\''")+"'"
    def build(self,artifact="both"):
        if not (self.android/"settings.gradle").exists(): raise FileNotFoundError("Native Android template is missing: android/settings.gradle")
        tasks=[]
        if artifact in {"apk","both"}: tasks.append(("apk","assembleRelease"))
        if artifact in {"aab","both"}: tasks.append(("aab","bundleRelease"))
        outputs={}
        for kind,task in tasks:
            self.log(f"[gradle] {task}"); proc=self._run(task)
            if proc.returncode!=0: raise RuntimeError(f"Gradle {task} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
            ext=kind; candidates=sorted(self.android.rglob(f"*.{ext}"),key=lambda p:p.stat().st_mtime,reverse=True)
            if not candidates: raise RuntimeError(f"Gradle completed but no .{ext} artifact was produced.")
            src=candidates[0]; outdir=self.root/"build"/kind; outdir.mkdir(parents=True,exist_ok=True); dest=outdir/src.name; shutil.copy2(src,dest); outputs[kind]=str(dest); self.log(f"[gradle] {kind.upper()}: {dest}")
        return outputs
    @staticmethod
    def ensure_wrapper(android_dir): return shutil.which("gradle") is not None or (Path(android_dir)/"gradlew").exists() or (os.name=="nt" and shutil.which("wsl.exe") is not None)
