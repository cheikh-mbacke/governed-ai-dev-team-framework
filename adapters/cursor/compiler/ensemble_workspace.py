"""Render a Cursor/VS Code multi-root workspace for the active ensemble."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governed_ai.core.ensemble_workspace import active_ensemble_folders
from governed_ai.core.workspace import Workspace


def render_code_workspace(folders: list[dict[str, str]], *, name: str) -> dict[str, Any]:
    """Return a ``.code-workspace`` document listing only the given folders."""
    return {
        "folders": [{"name": item["name"], "path": item["path"]} for item in folders],
        "settings": {},
    }


def write_active_ensemble_workspace(workspace: Workspace) -> Path | None:
    """Write ``<ensemble-id>.code-workspace`` at the instance root, or skip."""
    ensemble_id = workspace.active_ensemble_id
    if not ensemble_id:
        return None
    folders = active_ensemble_folders(workspace)
    document = render_code_workspace(folders, name=ensemble_id)
    path = workspace.instance_root / f"{ensemble_id}.code-workspace"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path
