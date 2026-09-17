"""Apply managed copy-plan entries to a target project."""

from __future__ import annotations

import shutil
from pathlib import Path

from distribution.installer.adapter_registry import ADAPTERS
from distribution.installer.agents_md import write_agents_md
from distribution.installer.source_files import CopyPlanEntry, materialize_adapter_dir

_COMPILED_DIR_TO_ADAPTER_ID = {
    registration.compiled_dir_item: adapter_id for adapter_id, registration in ADAPTERS.items()
}


def apply_copy_entries(
    source_root: Path,
    target: Path,
    entries: list[CopyPlanEntry],
    *,
    project_id: str | None = None,
) -> None:
    touched_adapter_id: str | None = None
    for entry in entries:
        if entry.action == "unchanged":
            continue
        if entry.relative.as_posix() == "AGENTS.md":
            write_agents_md(entry.destination, entry.source)
            continue
        top = entry.relative.parts[0] if entry.relative.parts else None
        if top in _COMPILED_DIR_TO_ADAPTER_ID:
            touched_adapter_id = _COMPILED_DIR_TO_ADAPTER_ID[top]
            continue
        entry.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry.source, entry.destination)
    if touched_adapter_id is not None:
        materialize_adapter_dir(
            source_root, target, project_id, active_adapter_id=touched_adapter_id
        )


def collect_changed_destinations(entries: list[CopyPlanEntry]) -> list[Path]:
    return [entry.destination for entry in entries if entry.action != "unchanged"]
