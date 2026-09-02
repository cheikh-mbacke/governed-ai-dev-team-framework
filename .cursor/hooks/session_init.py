#!/usr/bin/env python3
import json
import os
from pathlib import Path

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()


def _repository_kind(profile_path: Path) -> str | None:
    if not profile_path.is_file():
        return None
    for line in profile_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


message = (
    "Governed AI Team framework detected. Read .fabric/project-profile.yaml (fabrication) "
    "or .ai-team/project-profile.yaml (installed client) before inferring how this "
    "repository is organized."
)
fabric_profile = root / ".fabric" / "project-profile.yaml"
if _repository_kind(fabric_profile) == "framework_source":
    message += (
        " Workspace mode: framework_source (fabrication). See AGENTS.md."
        " Installed-client reference: tests/fixtures/projects/clean/."
    )
else:
    message += (
        " Read .ai-team/state/project-state.yaml before runtime activation."
    )
print(json.dumps({"additional_context": message}))
