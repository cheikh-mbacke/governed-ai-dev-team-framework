"""Append-only operational journal with corrupt-event isolation."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.persistence.atomic import atomic_write_text
from governed_ai.core.supervisor.file_lock import exclusive_file_lock
from governed_ai.core.supervisor.paths import ensure_supervisor_layout, journal_dir

CURSOR_NAME = "cursor.json"
CORRUPT_DIRNAME = "corrupt"
LOCK_NAME = "journal.lock"


def _cursor_path(ai_team: Path) -> Path:
    return journal_dir(ai_team) / CURSOR_NAME


def _events_dir(ai_team: Path) -> Path:
    return journal_dir(ai_team) / "events"


def _corrupt_dir(ai_team: Path) -> Path:
    return journal_dir(ai_team) / CORRUPT_DIRNAME


def _load_cursor(ai_team: Path) -> dict[str, Any]:
    path = _cursor_path(ai_team)
    if not path.is_file():
        return {"schema_version": 1, "last_sequence": 0, "last_event_id": None}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "last_sequence": 0, "last_event_id": None}
    return document if isinstance(document, dict) else {
        "schema_version": 1,
        "last_sequence": 0,
        "last_event_id": None,
    }


def _save_cursor(ai_team: Path, document: dict[str, Any]) -> None:
    atomic_write_text(_cursor_path(ai_team), json.dumps(document, indent=2, sort_keys=True))


def append_event(
    ai_team: Path,
    *,
    instance_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    work_unit_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Append one operational event. Payload must stay bounded (no secrets)."""
    ensure_supervisor_layout(ai_team)
    lock_path = journal_dir(ai_team) / LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        return _append_event_locked(
            ai_team,
            instance_id=instance_id,
            event_type=event_type,
            payload=payload,
            run_id=run_id,
            work_unit_id=work_unit_id,
            event_id=event_id,
        )


def _append_event_locked(
    ai_team: Path,
    *,
    instance_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    work_unit_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    events = _events_dir(ai_team)
    events.mkdir(parents=True, exist_ok=True)
    # Dedup by event_id if already present.
    resolved_event_id = event_id or None
    if resolved_event_id:
        for path in events.glob("*.json"):
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(prior, dict) and prior.get("event_id") == resolved_event_id:
                return prior

    for attempt in range(8):
        cursor = _load_cursor(ai_team)
        sequence = int(cursor.get("last_sequence") or 0) + 1
        event_uuid = resolved_event_id or f"EVT-{sequence:08d}-{uuid.uuid4().hex[:8]}"
        bounded_payload = dict(payload or {})
        for key, value in list(bounded_payload.items()):
            if isinstance(value, str) and len(value) > 2000:
                bounded_payload[key] = value[:2000] + "…[truncated]"
        document = {
            "schema_version": 1,
            "sequence": sequence,
            "event_id": event_uuid,
            "instance_id": instance_id,
            "run_id": run_id,
            "work_unit_id": work_unit_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": bounded_payload,
        }
        path = events / f"{sequence:08d}-{event_uuid}.json"
        # Exclusive create — concurrent sequence claim is rejected.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(path), flags)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(document, indent=2, sort_keys=True))
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        expected_sequence = sequence - 1
        current = _load_cursor(ai_team)
        if int(current.get("last_sequence") or 0) != expected_sequence:
            # Stale writer lost the CAS on the cursor — delete and retry.
            path.unlink(missing_ok=True)
            continue
        _save_cursor(
            ai_team,
            {
                "schema_version": 1,
                "last_sequence": sequence,
                "last_event_id": event_uuid,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        verify = _load_cursor(ai_team)
        if int(verify.get("last_sequence") or 0) != sequence:
            path.unlink(missing_ok=True)
            continue
        return document
    raise RuntimeError("journal append failed after concurrent retries")


def iter_events(
    ai_team: Path,
    *,
    after_sequence: int = 0,
) -> list[dict[str, Any]]:
    """Return ordered events after ``after_sequence``, isolating corrupt files."""
    ensure_supervisor_layout(ai_team)
    events = _events_dir(ai_team)
    events.mkdir(parents=True, exist_ok=True)
    corrupt = _corrupt_dir(ai_team)
    corrupt.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for path in sorted(events.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("event is not a mapping")
            if "sequence" not in document or "event_id" not in document:
                raise ValueError("event missing required fields")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            target = corrupt / path.name
            try:
                path.replace(target)
            except OSError:
                target = path
            alerts.append(
                {
                    "code": "corrupt_journal_event",
                    "path": str(target),
                    "error": str(exc),
                }
            )
            continue
        if int(document.get("sequence") or 0) <= after_sequence:
            continue
        results.append(document)
    if alerts:
        # Persist alerts beside the cursor so status/doctor can surface them.
        alert_path = journal_dir(ai_team) / "alerts.json"
        existing: list[dict[str, Any]] = []
        if alert_path.is_file():
            try:
                loaded = json.loads(alert_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    existing = loaded
            except (OSError, json.JSONDecodeError):
                existing = []
        existing.extend(alerts)
        atomic_write_text(alert_path, json.dumps(existing[-100:], indent=2))
    return results


def load_alerts(ai_team: Path) -> list[dict[str, Any]]:
    path = journal_dir(ai_team) / "alerts.json"
    if not path.is_file():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return document if isinstance(document, list) else []


def last_processed_sequence(ai_team: Path) -> int:
    return int(_load_cursor(ai_team).get("last_sequence") or 0)
