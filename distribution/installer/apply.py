"""Apply managed copy-plan entries to a target project."""

from __future__ import annotations

import shutil
from pathlib import Path

from distribution.installer.agents_md import write_agents_md
from distribution.installer.source_files import CopyPlanEntry, materialize_cursor_dir


def apply_copy_entries(
    source_root: Path,
    target: Path,
    entries: list[CopyPlanEntry],
    *,
    project_id: str | None = None,
) -> None:
    cursor_touched = False
    for entry in entries:
        if entry.action == "unchanged":
            continue
        if entry.relative.as_posix() == "AGENTS.md":
            write_agents_md(entry.destination, entry.source)
            continue
        if entry.relative.parts and entry.relative.parts[0] == ".cursor":
            cursor_touched = True
            continue
        entry.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry.source, entry.destination)
    if cursor_touched:
        materialize_cursor_dir(source_root, target, project_id=project_id)


def collect_changed_destinations(entries: list[CopyPlanEntry]) -> list[Path]:
    return [entry.destination for entry in entries if entry.action != "unchanged"]
