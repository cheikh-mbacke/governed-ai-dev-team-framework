"""G4 acceptance precondition checks (Document 14 SM-001 / SM-002)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.domain.work_unit.done import missing_done_prerequisites
from governed_ai.core.domain.work_unit.paths import find_work_unit_path


def work_units_to_verify(
    project_state: dict[str, Any],
    explicit_ids: list[str] | None,
) -> list[str]:
    if explicit_ids:
        return list(explicit_ids)
    work_units = project_state.get("work_units", {})
    return sorted(
        wu_id
        for wu_id, info in work_units.items()
        if info.get("status") not in {"done", "cancelled"}
    )


def verify_g4_preconditions(
    ai_team: Path,
    project_state: dict[str, Any],
    work_unit_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    verified: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    work_units_dir = ai_team / "work-units"

    for work_unit_id in work_unit_ids:
        path, ambiguity = find_work_unit_path(work_units_dir, work_unit_id)
        if ambiguity:
            failures.append({"work_unit_id": work_unit_id, "missing": [ambiguity]})
            continue
        if path is None:
            failures.append(
                {
                    "work_unit_id": work_unit_id,
                    "missing": ["work unit file not found"],
                }
            )
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        missing = missing_done_prerequisites(document)
        if missing:
            failures.append({"work_unit_id": work_unit_id, "missing": missing})
        else:
            verified.append(
                {
                    "work_unit_id": work_unit_id,
                    "status": "preconditions_satisfied",
                }
            )

    return verified, failures
