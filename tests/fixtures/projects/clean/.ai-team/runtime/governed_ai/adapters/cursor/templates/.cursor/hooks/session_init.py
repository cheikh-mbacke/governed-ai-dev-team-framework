#!/usr/bin/env python3
import json
import os
from pathlib import Path

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
profile = root / ".ai-team" / "project-profile.yaml"
state = root / ".ai-team" / "state" / "project-state.yaml"


def _repository_kind(profile_path: Path) -> str | None:
    if not profile_path.is_file():
        return None
    for line in profile_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


message = (
    "Governed AI Team framework detected. Before product changes, read "
    f"{profile.relative_to(root) if profile.exists() else '.ai-team/project-profile.yaml'} and "
    f"{state.relative_to(root) if state.exists() else '.ai-team/state/project-state.yaml'}. "
    "Use /compile-project before runtime activation when no approved execution plan exists."
)
if _repository_kind(profile) == "framework_source":
    message += (
        " This is a framework_source repository: edit src/ and adapters/, not "
        "tests/fixtures/projects/; do not create .ai-team/runtime/ or "
        "installation-record.json here; run sync_source_manifest.py after payload changes."
    )
print(json.dumps({"additional_context": message}))
