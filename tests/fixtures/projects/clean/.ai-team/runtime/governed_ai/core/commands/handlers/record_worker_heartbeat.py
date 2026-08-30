"""RecordWorkerHeartbeat command handler (orchestrator prerequisite, Document 6 §9.4).

Nothing previously refreshed `WorkerLease.heartbeat_at` after acquisition —
without this command, staleness detection (`stalled_after_minutes`) could
never reflect a worker that is actually still alive. Fencing-checked like
every other Run-scoped write: a heartbeat from a superseded epoch is
rejected, never silently accepted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.domain.run import fencing
from governed_ai.core.persistence.transaction import Transaction


def handle_record_worker_heartbeat(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    lease_id = envelope["target"]["id"]
    payload = envelope["payload"]
    run_id = payload["run_id"]
    epoch = payload["epoch"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/payload/run_id")
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    if (
        run_document.get("autonomy_preset", "supervised_copilots").startswith("unattended_")
        and run_document.get("status") != "active"
    ):
        raise GatewayError(ErrorCode.INVARIANT_VIOLATION, f"run {run_id!r} is not active")

    lease_path = workspace_root.ai_team / "runs" / "leases" / f"{lease_id}.yaml"
    if not lease_path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND, f"worker lease {lease_id!r} not found", "/target/id"
        )
    lease_document = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
    work_unit_id = lease_document["work_unit_id"]

    current = fencing.current_lease(run_document, work_unit_id)
    if (
        lease_document.get("status") != "active"
        or current is None
        or current.get("lease_id") != lease_id
    ):
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"worker lease {lease_id!r} is not the current active lease",
            "/target/id",
        )

    if not fencing.is_epoch_current(run_document, work_unit_id, epoch):
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"stale worker lease epoch for work unit {work_unit_id!r}",
            "/payload/epoch",
        )

    now_iso = datetime.now(UTC).isoformat()
    lease_document["heartbeat_at"] = now_iso
    transaction.plan_yaml_write(lease_path, lease_document)

    return {
        "affected": [{"kind": "worker_lease", "id": lease_id, "heartbeat_at": now_iso}],
    }, []
