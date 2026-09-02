"""ReleaseWorkerLease handler — close a lease and free Run parallelism capacity."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run import fencing
from governed_ai.core.persistence.transaction import Transaction


def handle_release_worker_lease(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    lease_id = envelope["target"]["id"]
    payload = envelope["payload"]
    run_id = payload["run_id"]
    work_unit_id = payload["work_unit_id"]
    epoch = payload["epoch"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/payload/run_id")
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    current = fencing.current_lease(run_document, work_unit_id)
    if (
        current is None
        or current.get("lease_id") != lease_id
        or current.get("epoch") != epoch
    ):
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"lease {lease_id!r} is not current for work unit {work_unit_id!r}",
            "/payload/epoch",
        )

    lease_path = workspace_root.ai_team / "runs" / "leases" / f"{lease_id}.yaml"
    if not lease_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"worker lease {lease_id!r} not found", "/target/id")
    lease_document = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
    if lease_document.get("status") != "active":
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"worker lease {lease_id!r} is not active",
            "/target/id",
        )

    now = datetime.now(UTC).isoformat()
    lease_document["status"] = "released"
    lease_document["released_at"] = now
    lease_document["release_reason"] = payload.get("reason", "workflow step completed")
    validate_against_schema(
        workspace_root.ai_team,
        lease_document,
        "worker-lease.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(lease_path, lease_document)

    del run_document["leases_by_work_unit"][work_unit_id]
    run_document["updated_at"] = now
    transaction.plan_yaml_write(run_path, run_document)
    return {
        "affected": [
            {"kind": "worker_lease", "id": lease_id, "status": "released"},
            {"kind": "run", "id": run_id, "revision": run_document.get("revision")},
        ]
    }, []
