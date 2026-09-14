"""File-backed durable work queue with delayed visibility and dead-letter."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from governed_ai.compat.datetime import UTC, datetime, timedelta
from governed_ai.core.persistence.atomic import atomic_write_text
from governed_ai.core.supervisor.file_lock import exclusive_file_lock
from governed_ai.core.supervisor.paths import (
    dead_letter_dir,
    ensure_supervisor_layout,
    queue_dir,
)
from governed_ai.core.supervisor.protocol import WorkerAttemptState

QUEUE_LOCK_NAME = "queue.lock"


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _item_path(ai_team: Path, item_id: str) -> Path:
    return queue_dir(ai_team) / f"{item_id}.json"


def _dead_letter_path(ai_team: Path, item_id: str) -> Path:
    return dead_letter_dir(ai_team) / f"{item_id}.json"


def _write_item(path: Path, document: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(document, indent=2, sort_keys=True))


def _read_item(path: Path) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def enqueue(
    ai_team: Path,
    *,
    run_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    delay_seconds: float = 0.0,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    ensure_supervisor_layout(ai_team)
    lock_path = queue_dir(ai_team) / QUEUE_LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        return _enqueue_locked(
            ai_team,
            run_id=run_id,
            kind=kind,
            payload=payload,
            delay_seconds=delay_seconds,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
        )


def _enqueue_locked(
    ai_team: Path,
    *,
    run_id: str,
    kind: str,
    payload: dict[str, Any] | None,
    delay_seconds: float,
    dedupe_key: str | None,
    max_attempts: int,
) -> dict[str, Any]:
    if dedupe_key:
        for existing in list_items(ai_team):
            if existing.get("dedupe_key") == dedupe_key and existing.get("state") in {
                "queued",
                "leased",
                "acknowledged",
            }:
                return existing
    now = _now()
    item_id = f"Q-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    visible_at = now + timedelta(seconds=max(0.0, delay_seconds))
    document = {
        "schema_version": 1,
        "id": item_id,
        "run_id": run_id,
        "kind": kind,
        "state": "queued",
        "worker_attempt_state": WorkerAttemptState.QUEUED.value,
        "payload": dict(payload or {}),
        "attempt_count": 0,
        "max_attempts": max(1, int(max_attempts)),
        "next_attempt_at": visible_at.isoformat(),
        "lease_id": None,
        "lease_epoch": 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "dedupe_key": dedupe_key,
        "last_error": None,
    }
    _write_item(_item_path(ai_team, item_id), document)
    return document


def list_items(ai_team: Path, *, include_dead_letter: bool = False) -> list[dict[str, Any]]:
    ensure_supervisor_layout(ai_team)
    items: list[dict[str, Any]] = []
    for path in sorted(queue_dir(ai_team).glob("*.json")):
        document = _read_item(path)
        if document is not None:
            items.append(document)
    if include_dead_letter:
        for path in sorted(dead_letter_dir(ai_team).glob("*.json")):
            document = _read_item(path)
            if document is not None:
                items.append(document)
    return items


def lease_next(
    ai_team: Path,
    *,
    worker_id: str,
    visibility_timeout_seconds: float = 60.0,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Lease one visible queued item."""
    lock_path = queue_dir(ai_team) / QUEUE_LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        return _lease_next_locked(
            ai_team,
            worker_id=worker_id,
            visibility_timeout_seconds=visibility_timeout_seconds,
            now=now,
        )


def _lease_next_locked(
    ai_team: Path,
    *,
    worker_id: str,
    visibility_timeout_seconds: float = 60.0,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    observed = now or _now()
    for item in list_items(ai_team):
        if item.get("state") != "queued":
            continue
        visible_at = _parse_time(item.get("next_attempt_at")) or observed
        if visible_at > observed:
            continue
        path = _item_path(ai_team, str(item["id"]))
        current = _read_item(path)
        if current is None or current.get("state") != "queued":
            continue
        lease_id = f"QL-{uuid.uuid4().hex[:12]}"
        epoch = int(current.get("lease_epoch") or 0) + 1
        current["state"] = "leased"
        current["worker_attempt_state"] = WorkerAttemptState.LEASED.value
        current["lease_id"] = lease_id
        current["lease_epoch"] = epoch
        current["leased_by"] = worker_id
        current["attempt_count"] = int(current.get("attempt_count") or 0) + 1
        current["lease_expires_at"] = (
            observed + timedelta(seconds=max(1.0, visibility_timeout_seconds))
        ).isoformat()
        current["updated_at"] = observed.isoformat()
        _write_item(path, current)
        verify = _read_item(path)
        if (
            verify is None
            or verify.get("lease_id") != lease_id
            or int(verify.get("lease_epoch") or 0) != epoch
        ):
            continue
        return verify
    return None


def acknowledge(
    ai_team: Path,
    item_id: str,
    *,
    lease_id: str,
    lease_epoch: int,
    worker_attempt_state: str = WorkerAttemptState.RUNNING.value,
) -> dict[str, Any]:
    lock_path = queue_dir(ai_team) / QUEUE_LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        path = _item_path(ai_team, item_id)
        document = _read_item(path)
        if document is None:
            raise KeyError(item_id)
        if document.get("lease_id") != lease_id or int(document.get("lease_epoch") or 0) != lease_epoch:
            raise PermissionError("stale queue lease epoch")
        document["state"] = "acknowledged"
        document["worker_attempt_state"] = worker_attempt_state
        document["updated_at"] = _now().isoformat()
        _write_item(path, document)
        return document


def complete(
    ai_team: Path,
    item_id: str,
    *,
    lease_id: str,
    lease_epoch: int,
    worker_attempt_state: str = WorkerAttemptState.SUCCEEDED.value,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lock_path = queue_dir(ai_team) / QUEUE_LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        path = _item_path(ai_team, item_id)
        document = _read_item(path)
        if document is None:
            raise KeyError(item_id)
        if document.get("lease_id") != lease_id or int(document.get("lease_epoch") or 0) != lease_epoch:
            raise PermissionError("stale queue lease epoch")
        document["state"] = "completed"
        document["worker_attempt_state"] = worker_attempt_state
        document["result"] = dict(result or {})
        document["updated_at"] = _now().isoformat()
        _write_item(path, document)
        return document


def fail(
    ai_team: Path,
    item_id: str,
    *,
    lease_id: str,
    lease_epoch: int,
    error: dict[str, Any],
    retry_delay_seconds: float = 5.0,
    worker_attempt_state: str = WorkerAttemptState.FAILED.value,
) -> dict[str, Any]:
    lock_path = queue_dir(ai_team) / QUEUE_LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        path = _item_path(ai_team, item_id)
        document = _read_item(path)
        if document is None:
            raise KeyError(item_id)
        if document.get("lease_id") != lease_id or int(document.get("lease_epoch") or 0) != lease_epoch:
            raise PermissionError("stale queue lease epoch")
        document["last_error"] = error
        document["updated_at"] = _now().isoformat()
        if int(document.get("attempt_count") or 0) >= int(document.get("max_attempts") or 1):
            return dead_letter(ai_team, item_id, error=error, source=document)
        document["state"] = "queued"
        document["worker_attempt_state"] = WorkerAttemptState.QUEUED.value
        document["lease_id"] = None
        document["next_attempt_at"] = (
            _now() + timedelta(seconds=max(0.0, retry_delay_seconds))
        ).isoformat()
        document["worker_attempt_state_on_fail"] = worker_attempt_state
        _write_item(path, document)
        return document


def dead_letter(
    ai_team: Path,
    item_id: str,
    *,
    error: dict[str, Any],
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_supervisor_layout(ai_team)
    path = _item_path(ai_team, item_id)
    document = source or _read_item(path)
    if document is None:
        raise KeyError(item_id)
    document = dict(document)
    document["state"] = "dead_letter"
    document["worker_attempt_state"] = WorkerAttemptState.FAILED.value
    document["last_error"] = error
    document["updated_at"] = _now().isoformat()
    _write_item(_dead_letter_path(ai_team, item_id), document)
    path.unlink(missing_ok=True)
    return document


def reclaim_expired_leases(
    ai_team: Path,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    lock_path = queue_dir(ai_team) / QUEUE_LOCK_NAME
    with exclusive_file_lock(lock_path, timeout_seconds=15.0):
        observed = now or _now()
        reclaimed: list[dict[str, Any]] = []
        for item in list_items(ai_team):
            if item.get("state") not in {"leased", "acknowledged"}:
                continue
            expires = _parse_time(item.get("lease_expires_at"))
            if expires is None or expires > observed:
                continue
            path = _item_path(ai_team, str(item["id"]))
            current = _read_item(path)
            if current is None:
                continue
            current["state"] = "queued"
            current["worker_attempt_state"] = WorkerAttemptState.ORPHANED.value
            current["lease_id"] = None
            current["next_attempt_at"] = observed.isoformat()
            current["last_error"] = {
                "code": "lease_expired",
                "message": "queue lease visibility timeout elapsed",
            }
            current["updated_at"] = observed.isoformat()
            _write_item(path, current)
            reclaimed.append(current)
        return reclaimed
