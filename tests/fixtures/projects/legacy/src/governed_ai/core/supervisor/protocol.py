"""Worker / agent attempt lifecycle protocol."""

from __future__ import annotations

from enum import Enum


class WorkerAttemptState(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


TERMINAL_STATES = frozenset(
    {
        WorkerAttemptState.SUCCEEDED,
        WorkerAttemptState.FAILED,
        WorkerAttemptState.TIMED_OUT,
        WorkerAttemptState.CANCELLED,
        WorkerAttemptState.ORPHANED,
    }
)

ACTIVE_STATES = frozenset(
    {
        WorkerAttemptState.QUEUED,
        WorkerAttemptState.LEASED,
        WorkerAttemptState.STARTING,
        WorkerAttemptState.RUNNING,
    }
)


def is_terminal(state: str | WorkerAttemptState) -> bool:
    value = state.value if isinstance(state, WorkerAttemptState) else str(state)
    return value in {item.value for item in TERMINAL_STATES}


def can_transition(current: str | WorkerAttemptState, nxt: str | WorkerAttemptState) -> bool:
    current_value = current.value if isinstance(current, WorkerAttemptState) else str(current)
    next_value = nxt.value if isinstance(nxt, WorkerAttemptState) else str(nxt)
    if current_value == next_value:
        return True
    allowed = {
        WorkerAttemptState.QUEUED.value: {
            WorkerAttemptState.LEASED.value,
            WorkerAttemptState.CANCELLED.value,
        },
        WorkerAttemptState.LEASED.value: {
            WorkerAttemptState.STARTING.value,
            WorkerAttemptState.CANCELLED.value,
            WorkerAttemptState.ORPHANED.value,
        },
        WorkerAttemptState.STARTING.value: {
            WorkerAttemptState.RUNNING.value,
            WorkerAttemptState.FAILED.value,
            WorkerAttemptState.TIMED_OUT.value,
            WorkerAttemptState.CANCELLED.value,
            WorkerAttemptState.ORPHANED.value,
        },
        WorkerAttemptState.RUNNING.value: {
            WorkerAttemptState.SUCCEEDED.value,
            WorkerAttemptState.FAILED.value,
            WorkerAttemptState.TIMED_OUT.value,
            WorkerAttemptState.CANCELLED.value,
            WorkerAttemptState.ORPHANED.value,
        },
    }
    return next_value in allowed.get(current_value, set())
