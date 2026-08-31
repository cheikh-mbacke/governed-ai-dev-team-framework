"""Immediate, one-way Work Unit risk escalation during an unattended Run."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def handle_escalate_work_unit_risk(
    envelope: dict[str, Any], *, workspace_root, transaction: Transaction
) -> tuple[dict[str, Any], list[str]]:
    run_id = envelope["target"]["id"]
    expected_revision = envelope["target"]["expected_revision"]
    payload = envelope["payload"]
    work_unit_id = payload["work_unit_id"]
    new_class = payload["new_risk_class"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/target/id")
    run = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    if run.get("revision") != expected_revision:
        raise GatewayError(ErrorCode.CONFLICT, "run revision conflict", "/target/expected_revision")
    if work_unit_id not in (run.get("work_unit_ids") or []):
        raise GatewayError(ErrorCode.UNAUTHORIZED, "work unit is outside this run", "/payload/work_unit_id")
    if new_class not in RISK_ORDER:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "unknown risk class", "/payload/new_risk_class")

    work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
    if not work_unit_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"work unit {work_unit_id!r} not found", "/payload/work_unit_id")
    work_unit = yaml.safe_load(work_unit_path.read_text(encoding="utf-8"))
    previous_class = (work_unit.get("risk") or {}).get("class")
    if previous_class not in RISK_ORDER or RISK_ORDER[new_class] <= RISK_ORDER[previous_class]:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "risk can only move strictly upward during a run",
            "/payload/new_risk_class",
        )

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    work_unit.setdefault("risk", {})["class"] = new_class
    work_unit["risk"].setdefault("reasons", []).append(payload["reason"])
    maximum = ((run.get("effective_autonomy_policy") or {}).get("eligibility") or {}).get(
        "maximum_risk_class", "critical"
    )
    exceeds_maximum = RISK_ORDER[new_class] > RISK_ORDER.get(str(maximum), 3)
    critical_conflict = new_class == "critical" and any(
        other_id != work_unit_id
        and ((yaml.safe_load((workspace_root.ai_team / "work-units" / f"{other_id}.yaml").read_text(encoding="utf-8")) or {}).get("risk") or {}).get("class") == "critical"
        for other_id in (run.get("leases_by_work_unit") or {})
        if (workspace_root.ai_team / "work-units" / f"{other_id}.yaml").is_file()
    )
    paused = exceeds_maximum or critical_conflict
    if paused and work_unit.get("status") not in {"done", "cancelled"}:
        work_unit["status"] = "waiting_decision"
        lease_ref = (run.get("leases_by_work_unit") or {}).pop(work_unit_id, None)
        if lease_ref:
            lease_path = workspace_root.ai_team / "runs" / "leases" / f"{lease_ref['lease_id']}.yaml"
            if lease_path.is_file():
                lease = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
                lease["status"] = "released"
                lease["released_at"] = now_iso
                lease["release_reason"] = "risk escalation requires human review"
                transaction.plan_yaml_write(lease_path, lease)

    work_unit["revision"] = int(work_unit.get("revision", 1)) + 1
    work_unit["updated_at"] = now_iso
    run["revision"] = int(run.get("revision", 1)) + 1
    run["updated_at"] = now_iso
    transaction.plan_yaml_write(work_unit_path, work_unit)
    transaction.plan_yaml_write(run_path, run)

    event_id = f"EVT-{now:%Y%m%dT%H%M%SZ}-RISK-{work_unit_id}"
    transaction.plan_yaml_write(
        workspace_root.ai_team / "events" / f"{event_id}.yaml",
        {
            "id": event_id,
            "type": "RISK_ESCALATION",
            "work_unit": work_unit_id,
            "created_at": now_iso,
            "created_by_role": envelope["actor"]["role_id"],
            "summary": f"Risk escalated from {previous_class} to {new_class}.",
            "details": {
                "run_id": run_id,
                "previous_risk_class": previous_class,
                "new_risk_class": new_class,
                "reason": payload["reason"],
                "paused": paused,
            },
            "affected_nodes": [{"kind": "work_unit", "id": work_unit_id}],
            "requires_human": paused,
            "status": "open" if paused else "resolved",
        },
    )
    return {
        "affected": [
            {"kind": "work_unit", "id": work_unit_id, "revision": work_unit["revision"]},
            {"kind": "run", "id": run_id, "revision": run["revision"]},
        ],
        "details": {"previous_risk_class": previous_class, "new_risk_class": new_class, "paused": paused},
    }, [event_id]
