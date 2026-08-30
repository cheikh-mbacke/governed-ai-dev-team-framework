"""CloseRun command handler (Document 6 §9.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.domain.run.state_machine import is_transition_allowed
from governed_ai.core.domain.run.stop_conditions import GLOBAL_STOP_CONDITIONS
from governed_ai.core.persistence.transaction import Transaction

STOPPING_STATUSES = frozenset({"stopped", "failed"})


def handle_close_run(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    run_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    to_status = payload["status"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/target/id")

    document = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    if document.get("id") != run_id:
        raise GatewayError(ErrorCode.INVARIANT_VIOLATION, "run id mismatch", "/target/id")

    current_revision = document.get("revision", 1)
    if expected_revision != current_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current_revision}",
            "/target/expected_revision",
        )

    current_status = document.get("status")
    if not is_transition_allowed(current_status, to_status):
        raise GatewayError(
            ErrorCode.INVALID_TRANSITION,
            f"transition {current_status!r} -> {to_status!r} not allowed",
            "/payload/status",
        )

    stop_condition = payload.get("stop_condition")
    if to_status in STOPPING_STATUSES and stop_condition not in GLOBAL_STOP_CONDITIONS:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"unrecognized stop_condition {stop_condition!r}; must be one of {sorted(GLOBAL_STOP_CONDITIONS)}",
            "/payload/stop_condition",
        )

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    document["status"] = to_status
    document["revision"] = current_revision + 1
    document["closed_at"] = now_iso
    document["closed_reason"] = payload.get("reason")
    document["stop_condition"] = stop_condition if to_status in STOPPING_STATUSES else None
    document["updated_at"] = now_iso
    if to_status in STOPPING_STATUSES:
        for lease_ref in (document.get("leases_by_work_unit") or {}).values():
            lease_path = (
                workspace_root.ai_team / "runs" / "leases" / f"{lease_ref['lease_id']}.yaml"
            )
            if not lease_path.is_file():
                continue
            lease = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
            if lease.get("status") == "active":
                lease["status"] = "revoked"
                lease["released_at"] = now_iso
                lease["release_reason"] = f"run stopped: {stop_condition}"
                transaction.plan_yaml_write(lease_path, lease)
    transaction.plan_yaml_write(run_path, document)

    domain_events: list[str] = []
    if to_status in STOPPING_STATUSES:
        # Document 6 §9.5/§13 — a global stop condition is signalled immediately,
        # never deferred to the grouped morning report.
        event_id = f"EVT-{now:%Y%m%dT%H%M%SZ}-RUN-STOP-{run_id}"
        event_path = workspace_root.ai_team / "events" / f"{event_id}.yaml"
        event_document = {
            "id": event_id,
            "type": "BLOCKER",
            "work_unit": None,
            "created_at": now_iso,
            "created_by_role": "run-reliability-controller",
            "summary": f"Run {run_id} stopped entirely: {stop_condition}.",
            "details": {
                "run_id": run_id,
                "stop_condition": stop_condition,
                "reason": payload.get("reason"),
            },
            "affected_nodes": [{"kind": "run", "id": run_id}],
            "requires_human": True,
            "status": "open",
        }
        transaction.plan_yaml_write(event_path, event_document)
        domain_events.append(event_id)

    return {
        "affected": [
            {"kind": "run", "id": run_id, "revision": document["revision"], "status": to_status},
        ],
    }, domain_events
