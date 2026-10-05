"""Prompt templates for the MCP coder (jupris_agentic_brain). Kept in one place so the contract
the AI must follow is identical for chat-triggered fixes and the agentic loop."""
from __future__ import annotations

from typing import Any

from part1_builder.target_policy import load_policy

BUILDER_RULES = """\
Builder contract (immutable - change the game code, never the builder):
- Runs on Android via Buildozer/python-for-android, built inside WSL (Linux, case-sensitive paths).
- No Windows-only APIs or imports (win32*, winsound, msvcrt, ...).
- No hardcoded absolute paths. Use pathlib relative to the file: Path(__file__).parent / "assets" / "x.png".
- No pygame.font.SysFont. Use pygame.font.Font(None, size) (pygame's bundled font) or a project-relative .ttf.
- Display is device-managed: call pygame.display.set_mode((W, H), pygame.SCALED) or size (0, 0);
  never rely on a fixed desktop window size.
- Keep the entry point named main.py.
"""

OUTPUT_FORMAT = """\
Return ONLY the files you changed, each as a fenced block whose first line is `# file: relative/path.py`
and whose body is the COMPLETE new content of that file. Make minimal local edits to the listed problems;
do not rewrite unrelated code. No explanations outside the fenced blocks.
"""


def _finding_lines(findings: list[dict[str, Any]], limit: int = 40) -> str:
    rows = []
    for f in findings[:limit]:
        rows.append(f"- [{f.get('severity')}] {f.get('code')} {f.get('file')}:{f.get('line')} - "
                    f"{f.get('message')} (fix: {f.get('recommended_action', 'n/a')})")
    if len(findings) > limit:
        rows.append(f"- ... and {len(findings) - limit} more")
    return "\n".join(rows) or "- none"


def build_fix_prompt(findings: list[dict[str, Any]], unresolved_imports: list[dict[str, Any]] | None = None,
                     validation: dict[str, Any] | None = None, attempt: int = 1) -> str:
    policy = load_policy()
    parts = [
        BUILDER_RULES,
        f"Target: Google Play, Android API {policy['target_api']} (min {policy['min_api']}).",
        f"Fix attempt {attempt}. Problems found by the static analyzer:",
        _finding_lines(findings),
    ]
    if unresolved_imports:
        mods = sorted({m["module"] for m in unresolved_imports})
        parts.append("Imports that cannot be resolved (add the missing local module, or replace the "
                     "dependency with something available on Android): " + ", ".join(mods))
    if validation:
        failed = [k for k, v in validation.items() if k != "passed" and not v]
        if failed:
            parts.append("Failed validation checks: " + ", ".join(failed))
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)
