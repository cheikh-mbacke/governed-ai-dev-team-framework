#!/usr/bin/env python3
import json
import os
from pathlib import Path

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
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
print(json.dumps({"additional_context": message}))
