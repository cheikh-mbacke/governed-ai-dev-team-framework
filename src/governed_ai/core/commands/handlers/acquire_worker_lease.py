"""AcquireWorkerLease command handler — fencing entry point (Document 6 §9.4)."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime, timedelta
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run import fencing
from governed_ai.core.domain.run.parallelism import (
    DEFAULT_MAXIMUM_PARALLEL_WORKERS,
    active_worker_count,
)
from governed_ai.core.persistence.transaction import Transaction


def _lease_is_fresh(lease: dict[str, Any], *, now: datetime) -> bool:
    heartbeat_at = lease.get("heartbeat_at")
    stalled_after_minutes = lease.get("stalled_after_minutes", 15)
    if not heartbeat_at:
        return False
    heartbeat = datetime.fromisoformat(heartbeat_at)
    return now - heartbeat < timedelta(minutes=stalled_after_minutes)


def handle_acquire_worker_lease(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    lease_id = envelope["target"]["id"]
    payload = envelope["payload"]
    run_id = payload["run_id"]
    work_unit_id = payload["work_unit_id"]
    worker_id = payload["worker_id"]
    stalled_after_minutes = payload.get("stalled_after_minutes", 15)

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/payload/run_id")
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    if work_unit_id not in (run_document.get("work_unit_ids") or []):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"work unit {work_unit_id!r} is not part of run {run_id!r}",
            "/payload/work_unit_id",
        )
    if (
        run_document.get("autonomy_preset", "supervised_copilots").startswith("unattended_")
        and run_document.get("status") != "active"
    ):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"run {run_id!r} is not active",
            "/payload/run_id",
        )

    lease_path = workspace_root.ai_team / "runs" / "leases" / f"{lease_id}.yaml"
    if lease_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"worker lease {lease_id!r} already exists",
            "/target/id",
        )

    now = datetime.now(UTC)
    existing_lease_id = None
    existing_lease = fencing.current_lease(run_document, work_unit_id)
    if existing_lease is not None:
        existing_lease_id = existing_lease["lease_id"]
        existing_lease_path = (
            workspace_root.ai_team / "runs" / "leases" / f"{existing_lease_id}.yaml"
        )
        existing_lease_document = yaml.safe_load(
            existing_lease_path.read_text(encoding="utf-8")
        )
        if _lease_is_fresh(existing_lease_document, now=now):
            raise GatewayError(
                ErrorCode.CONFLICT,
                f"work unit {work_unit_id!r} already leased by an active worker",
                "/payload/work_unit_id",
            )
        # Reassignment: the stale lease is superseded, never mutated for reuse.
        existing_lease_document["status"] = "superseded"
        existing_lease_document["superseded_by"] = lease_id
        transaction.plan_yaml_write(existing_lease_path, existing_lease_document)
    else:
        # Document 6 §11 — a reassignment replaces a worker, it never grows
        # the active count, so the parallelism cap only applies to genuinely
        # new work being staffed.
        maximum_parallel_workers = run_document.get(
            "maximum_parallel_workers", DEFAULT_MAXIMUM_PARALLEL_WORKERS
        )
        if active_worker_count(run_document) >= maximum_parallel_workers:
            raise GatewayError(
                ErrorCode.CONFLICT,
                f"run {run_id!r} already has {maximum_parallel_workers} active workers",
                "/payload/work_unit_id",
            )
        work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
        work_unit = (
            yaml.safe_load(work_unit_path.read_text(encoding="utf-8"))
            if work_unit_path.is_file()
            else {}
        )
        if (work_unit.get("risk") or {}).get("class") == "critical":
            for leased_work_unit_id in (run_document.get("leases_by_work_unit") or {}):
                leased_path = (
                    workspace_root.ai_team / "work-units" / f"{leased_work_unit_id}.yaml"
                )
                leased = (
                    yaml.safe_load(leased_path.read_text(encoding="utf-8"))
                    if leased_path.is_file()
                    else {}
                )
                if (leased.get("risk") or {}).get("class") == "critical":
                    raise GatewayError(
                        ErrorCode.CONFLICT,
                        "only one critical Work Unit may hold an active lease",
                        "/payload/work_unit_id",
                    )

    epoch = fencing.next_epoch(run_document, work_unit_id)

    lease_document = {
        "id": lease_id,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "worker_id": worker_id,
        "epoch": epoch,
        "status": "active",
        "heartbeat_at": now.isoformat(),
        "stalled_after_minutes": stalled_after_minutes,
        "created_at": now.isoformat(),
        "superseded_by": None,
    }
    validate_against_schema(
        workspace_root.ai_team,
        lease_document,
        "worker-lease.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(lease_path, lease_document)

    run_document.setdefault("leases_by_work_unit", {})
    run_document["leases_by_work_unit"][work_unit_id] = {
        "lease_id": lease_id,
        "epoch": epoch,
    }
    run_document["updated_at"] = now.isoformat()
    transaction.plan_yaml_write(run_path, run_document)

    return {
        "affected": [
            {"kind": "worker_lease", "id": lease_id, "epoch": epoch, "status": "active"},
            {"kind": "run", "id": run_id, "revision": run_document.get("revision")},
        ],
    }, []
