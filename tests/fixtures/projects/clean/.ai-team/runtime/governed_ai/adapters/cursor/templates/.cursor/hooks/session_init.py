#!/usr/bin/env python3
import json
import os
from pathlib import Path

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
profile = root / ".ai-team" / "project-profile.yaml"
state = root / ".ai-team" / "state" / "project-state.yaml"
message = (
    "Governed AI Team framework detected. Before product changes, read "
    f"{profile.relative_to(root) if profile.exists() else '.ai-team/project-profile.yaml'} and "
    f"{state.relative_to(root) if state.exists() else '.ai-team/state/project-state.yaml'}. "
    "Use /compile-project before runtime activation when no approved execution plan exists."
)
print(json.dumps({"additional_context": message}))
