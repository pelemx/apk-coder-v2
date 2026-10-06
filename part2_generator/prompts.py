"""Prompt contract for JuprisX HTML/JS Android generation."""
from __future__ import annotations
from typing import Any

BUILDER_RULES = """\
Builder contract (immutable - HTML5/JS/CSS to Android):
- Output is a local/offline-first Android WebView application.
- Generate HTML5, CSS and JavaScript only for the app payload. Do not generate Python/Pygame.
- Main web entry point MUST be web/index.html.
- Use mobile-first responsive layout and include a viewport meta tag.
- Prefer Canvas/DOM/Pointer Events for games and touch UI; support touch and mouse/pointer fallback.
- All scripts, styles, fonts, images and audio used at runtime MUST be local project files.
- NEVER reference a CDN, remote script, http:// resource, desktop absolute path, or file:// URL.
- Use relative paths from web/ and keep generated assets under web/assets/.
- If Phaser or another engine is requested, bundle its runtime locally under web/assets/.
- Do not assume Node.js, npm, React Native, Cordova or a network connection at runtime.
- Android packaging is performed by the native Gradle WebView container; do not generate Android build scripts in the web payload.
"""

OUTPUT_FORMAT = """\
Return ONLY the files changed, each as a fenced block whose first line is `# file: relative/path`.
The body MUST contain the COMPLETE new content of that file. No explanations outside fenced blocks.
"""


def _finding_lines(findings: list[dict[str, Any]], limit: int = 50) -> str:
    rows = []
    for f in findings[:limit]:
        rows.append(f"- [{f.get('severity')}] {f.get('code')} {f.get('file')}:{f.get('line')} - {f.get('message')} (fix: {f.get('recommended_action', 'n/a')})")
    if len(findings) > limit:
        rows.append(f"- ... and {len(findings) - limit} more")
    return "\n".join(rows) or "- none"


def build_fix_prompt(findings: list[dict[str, Any]], unresolved_imports=None,
                     validation: dict[str, Any] | None = None, attempt: int = 1) -> str:
    parts = [BUILDER_RULES, f"Fix attempt {attempt}.", "Static analyzer findings:", _finding_lines(findings)]
    if validation:
        failed = [k for k, v in validation.items() if k not in {"passed", "findings"} and not v]
        if failed:
            parts.append("Failed validation checks: " + ", ".join(failed))
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)
