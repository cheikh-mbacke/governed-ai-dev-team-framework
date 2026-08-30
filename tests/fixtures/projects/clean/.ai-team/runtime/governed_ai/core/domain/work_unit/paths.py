"""Work Unit path resolution under .ai-team/work-units/."""

from __future__ import annotations

from pathlib import Path

import yaml


def find_work_unit_path(work_units_dir: Path, work_unit_id: str) -> tuple[Path | None, str | None]:
    """Resolve a Work Unit file by id, prefix, or embedded id field."""
    exact = work_units_dir / f"{work_unit_id}.yaml"
    if exact.exists():
        return exact, None

    prefix_matches = sorted(work_units_dir.glob(f"{work_unit_id}-*.yaml"))
    if len(prefix_matches) == 1:
        return prefix_matches[0], None
    if len(prefix_matches) > 1:
        return None, (
            f"multiple files match '{work_unit_id}-*.yaml': "
            f"{[path.name for path in prefix_matches]}"
        )

    for path in sorted(work_units_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id") == work_unit_id:
            return path, None

    return None, None
