"""Typed progress events for the gateway / supervisor boundary."""

from __future__ import annotations

from enum import Enum
from typing import Any

from governed_ai.compat.datetime import UTC, datetime


class ProgressEventType(str, Enum):
    PROCESS_STARTED = "process_started"
    CONTEXT_LOADED = "context_loaded"
    FILES_INSPECTED = "files_inspected"
    MODIFICATION_STARTED = "modification_started"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    RESULT_SUBMITTED = "result_submitted"


# Events that update last_useful_progress (business-meaningful transitions).
_USEFUL_PROGRESS = frozenset(
    {
        ProgressEventType.MODIFICATION_STARTED,
        ProgressEventType.VERIFICATION_COMPLETED,
        ProgressEventType.RESULT_SUBMITTED,
    }
)


def is_useful_progress(event_type: ProgressEventType | str) -> bool:
    """Return True when the event should refresh last_useful_progress.

    Heartbeats and pure liveness signals must NOT use these event types.
    ``process_started``, ``context_loaded``, ``files_inspected``, and
    ``verification_started`` are operational observability only.
    """
    if isinstance(event_type, str):
        try:
            event_type = ProgressEventType(event_type)
        except ValueError:
            return False
    return event_type in _USEFUL_PROGRESS


def make_progress_event(
    event_type: ProgressEventType,
    *,
    execution_id: str,
    run_id: str,
    work_unit_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_type": event_type.value,
        "useful_progress": is_useful_progress(event_type),
        "execution_id": execution_id,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload or {},
    }
