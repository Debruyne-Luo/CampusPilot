"""Idempotent pinned-source patch: register only the CampusPilot editable surface.

No optimizer algorithm, task selection, memory or scoring behavior is changed.
"""

import pathlib
import subprocess
import sys

PIN = "1cfe254e8d25b15f37048c3730134686abe60335"
MARKER = "# CampusPilot surface registration (application-owned extension)"
INSERT = '''        "campuspilot": _SurfaceText(
            surface_md="""# WHAT YOU CAN CHANGE
Only answer_guidance.md and tool_guidance.md are editable UTF-8 text (6000 chars each).
These files advise the existing CampusPilot AgentRunner, not OpenCode's task solver.
There are no editable scripts, plugins, skills, memory facts, tools or subagents.
Do not add university facts or expected answers. Do not change permissions, schemas,
citations, safety rules or judge thresholds. Omitted files inherit the prior content.
Edit the files directly under context/harness and return notes with execution evidence.
""",
            inv="Improve general answer completeness and use of the existing read-only tools.",
            dom="Improve source-grounded campus guidance without adding factual knowledge.",
            tts_surface="Only answer_guidance.md and tool_guidance.md are editable.",
        ),
'''


def patch(root: pathlib.Path) -> None:
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != PIN:
        raise ValueError("Unexpected upstream revision")
    path = root / "harness2/core/prompts.py"
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    original = subprocess.check_output(
        ["git", "-C", str(root), "show", "HEAD:harness2/core/prompts.py"]
    )
    if original.decode("utf-8").replace("\r\n", "\n") != text:
        raise ValueError("Refuse to overwrite unrelated upstream edits")
    anchor = '    return {\n        "opencode": _SurfaceText('
    if text.count(anchor) != 1:
        raise ValueError("Pinned registration seam missing")
    text = text.replace(
        anchor, "    " + MARKER + "\n    return {\n" + INSERT + '        "opencode": _SurfaceText('
    )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch(pathlib.Path(sys.argv[1]).resolve())
