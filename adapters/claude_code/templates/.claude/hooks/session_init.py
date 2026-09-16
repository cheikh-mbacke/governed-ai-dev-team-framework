#!/usr/bin/env python3
"""SessionStart hook: inject framework-source-vs-installed-project context.

Ported from adapters/cursor/templates/.cursor/hooks/session_init.py — the
message logic is unchanged. Output uses Claude Code's
"hookSpecificOutput.additionalContext" shape — VERIFIED 2026-09-16: a real
`claude -p` session's persisted transcript showed this hook's exact stdout
recorded as a "hook_success" attachment, and its additionalContext text
appearing verbatim as a following "hook_additional_context" attachment
actually injected into the conversation before the first user message.
"""
import json
import os
from pathlib import Path

env_root = os.environ.get("CLAUDE_PROJECT_DIR")
root = Path(env_root).resolve() if env_root else Path(".").resolve()
profile = root / ".ai-team" / "project-profile.yaml"


def _repository_kind(profile_path: Path) -> str | None:
    if not profile_path.is_file():
        return None
    for line in profile_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


message = (
    "Governed AI Team framework detected. Read .ai-team/project-profile.yaml before "
    "inferring how this repository is organized."
)
if _repository_kind(profile) == "framework_source":
    message += (
        " Workspace mode: framework_source (fabrication). This repo builds the framework;"
        " it is not an installed client project and does not run compile-project or"
        " client Work Unit cycles here. project-state.yaml is a virgin template only."
        " Edit src/ and adapters/. Installed-layout reference:"
        " tests/fixtures/projects/clean/. Never run tools/install.py --target . here."
    )
else:
    message += (
        " Read .ai-team/state/project-state.yaml before runtime activation when no"
        " approved execution plan exists. Use /compile-project when required."
    )
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": message,
    },
}))
