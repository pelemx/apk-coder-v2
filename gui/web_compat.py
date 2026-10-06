"""Runtime compatibility patch for the HTML/JS Android builder GUI."""
from __future__ import annotations


def apply_web_compat(AppWindow):
    """Replace legacy WSL/Buildozer setup behavior without rewriting the GUI shell."""
    def setup_environment(self):
        self.set_status("● Checking Android Toolchain")
        self._notify("Checking native Android build environment (JDK, Android SDK, Gradle, keytool)...")
        def work():
            from part1_builder.wsl_checker import apply_setup
            return apply_setup(log=self._bg_log)
        def done(env, error):
            self.set_status("● Idle")
            if error:
                self._notify(f"Android toolchain check failed: {error}")
            elif env.get("ready"):
                self._notify("Android build environment ready (JDK, Android SDK, Gradle, keytool).")
            else:
                self._notify("Android environment incomplete: " + "; ".join(env.get("errors", []) or ["see Log"]))
        self._run_bg(work, done)
    AppWindow.setup_environment = setup_environment
    return AppWindow
