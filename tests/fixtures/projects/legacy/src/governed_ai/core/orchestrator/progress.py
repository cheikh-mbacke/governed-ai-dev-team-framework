"""Observe useful Run progress separately from process/lease liveness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime, timedelta
from governed_ai.core.domain.run.autonomy_policy import resolve_step_timeout_seconds


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _yaml_documents(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    documents: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(document, dict):
            documents.append(document)
    return documents


def evaluate_run_progress(
    ai_team: Path,
    run_document: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return `working`, `progressing`, or `stalled_no_progress` for an active Run.

    Lease heartbeats prove only that a process is alive and deliberately do not
    count as useful progress.  A currently started attempt is considered valid
    work until its governed per-step timeout, preventing long implementation
    calls from being mistaken for idle spin.
    """
    observed_at = now or datetime.now(UTC)
    run_id = str(run_document.get("id") or "")
    if run_document.get("status") != "active":
        return {
            "state": "terminal",
            "run_id": run_id,
            "last_progress_at": run_document.get("updated_at"),
            "minutes_without_progress": 0.0,
            "active_attempt_ids": [],
        }

    candidates = [
        value
        for value in (
            _timestamp(run_document.get("created_at")),
            _timestamp(run_document.get("opened_at")),
        )
        if value is not None
    ]
    work_unit_ids = {str(item) for item in run_document.get("work_unit_ids") or []}
    for work_unit_id in work_unit_ids:
        path = ai_team / "work-units" / f"{work_unit_id}.yaml"
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        updated = _timestamp(document.get("updated_at"))
        if updated is not None:
            candidates.append(updated)

    attempts = [
        item
        for item in _yaml_documents(ai_team / "runs" / "execution-attempts")
        if item.get("run_id") == run_id
    ]
    current_lease_ids = {
        str(ref.get("lease_id"))
        for ref in (run_document.get("leases_by_work_unit") or {}).values()
        if ref.get("lease_id")
    }
    active_attempt_ids: list[str] = []
    active_deadlines: list[datetime] = []
    for attempt in attempts:
        if attempt.get("status") == "started":
            started = _timestamp(attempt.get("started_at"))
            if started is not None and str(attempt.get("worker_lease_id")) in current_lease_ids:
                timeout = resolve_step_timeout_seconds(
                    run_document.get("effective_autonomy_policy"),
                    str(attempt.get("step") or ""),
                )
                active_attempt_ids.append(str(attempt.get("id")))
                active_deadlines.append(started + timedelta(seconds=timeout))
            continue
        ended = _timestamp(attempt.get("ended_at"))
        if ended is not None:
            candidates.append(ended)

    last_progress = max(candidates) if candidates else observed_at
    minutes = max(0.0, (observed_at - last_progress).total_seconds() / 60.0)
    threshold = float(
        ((run_document.get("effective_autonomy_policy") or {}).get("execution") or {}).get(
            "stalled_after_minutes", 15
        )
    )
    if active_deadlines and max(active_deadlines) > observed_at:
        state = "working"
    elif minutes >= threshold:
        state = "stalled_no_progress"
    else:
        state = "progressing"
    return {
        "state": state,
        "run_id": run_id,
        "last_progress_at": last_progress.isoformat(),
        "minutes_without_progress": round(minutes, 2),
        "stalled_after_minutes": threshold,
        "active_attempt_ids": active_attempt_ids,
    }
