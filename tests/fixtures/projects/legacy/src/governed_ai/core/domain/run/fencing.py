"""Worker-lease epoch fencing helpers (Document 6 §2.6, §9.4).

A `Run` document tracks, per Work Unit, which `WorkerLease` currently holds
authority to write on its behalf (`leases_by_work_unit[work_unit_id]`). Every
reassignment increments the epoch. Any command referencing a stale epoch must
be rejected deterministically by the Core — never inferred by an agent.
"""

from __future__ import annotations

from typing import Any


class FencingError(ValueError):
    """Invalid or missing lease/epoch bookkeeping on a Run document."""


def leases_by_work_unit(run_document: dict[str, Any]) -> dict[str, Any]:
    return run_document.get("leases_by_work_unit") or {}


def current_lease(run_document: dict[str, Any], work_unit_id: str) -> dict[str, Any] | None:
    return leases_by_work_unit(run_document).get(work_unit_id)


def current_epoch(run_document: dict[str, Any], work_unit_id: str) -> int:
    lease = current_lease(run_document, work_unit_id)
    if lease is None:
        raise FencingError(f"work unit {work_unit_id!r} has no active lease on this run")
    epoch = lease.get("epoch")
    if not isinstance(epoch, int):
        raise FencingError(f"lease epoch for {work_unit_id!r} must be an integer")
    return epoch


def is_epoch_current(run_document: dict[str, Any], work_unit_id: str, epoch: int) -> bool:
    try:
        return current_epoch(run_document, work_unit_id) == epoch
    except FencingError:
        return False


def next_epoch(run_document: dict[str, Any], work_unit_id: str) -> int:
    lease = current_lease(run_document, work_unit_id)
    if lease is None:
        return 1
    return current_epoch(run_document, work_unit_id) + 1
