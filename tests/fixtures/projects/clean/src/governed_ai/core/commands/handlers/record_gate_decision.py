"""RecordGateDecision command handler."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.gates import G4_COMPLETION_STATUSES, GATE_STATUS_BY_GATE, HUMAN_ACCEPTANCE_BY_GATE_STATUS
from governed_ai.core.domain.gates.g4_preconditions import verify_g4_preconditions, work_units_to_verify
from governed_ai.core.domain.gates.naming import generate_gate_decision_id
from governed_ai.core.domain.work_unit.paths import find_work_unit_path
from governed_ai.core.persistence.transaction import Transaction


def handle_record_gate_decision(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    gate = payload.get("gate")
    status = payload.get("status")
    by = payload.get("by")
    if gate not in GATE_STATUS_BY_GATE:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.gate must be G0-G4", "/payload/gate")
    if status not in GATE_STATUS_BY_GATE[gate]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"status {status!r} not allowed for {gate}",
            "/payload/status",
        )
    if not by:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.by is required", "/payload/by")

    state_path = workspace_root.ai_team / "state" / "project-state.yaml"
    if not state_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, "project state not found", "/payload/gate")

    project_state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    work_unit_ids = payload.get("work_unit_ids") or []
    if isinstance(work_unit_ids, str):
        work_unit_ids = [item.strip() for item in work_unit_ids.split(",") if item.strip()]

    preconditions_verified: list[dict[str, Any]] = []
    if gate == "G4" and status in G4_COMPLETION_STATUSES:
        to_verify = work_units_to_verify(project_state, work_unit_ids or None)
        verified, failures = verify_g4_preconditions(workspace_root.ai_team, project_state, to_verify)
        if failures:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"G4 preconditions not satisfied: {failures}",
                "/payload/gate",
            )
        preconditions_verified = verified

    now = datetime.now(UTC).isoformat()
    gate_decision_id = generate_gate_decision_id(gate)
    decision = {
        "id": gate_decision_id,
        "gate": gate,
        "status": status,
        "by": by,
        "at": now,
        "note": payload.get("note", ""),
    }
    validate_against_schema(
        workspace_root.ai_team,
        decision,
        "gate-decision.schema.json",
        root_path="",
    )

    project_state.setdefault("gates", {}).setdefault(gate, {})
    project_state["gates"][gate] = {
        "status": status,
        "by": by,
        "at": now,
        "note": payload.get("note", ""),
    }
    if gate == "G1" and status == "approved":
        project_state["phase"] = "execution"
    elif gate == "G0" and status in {"rejected", "failed", "changes_requested"}:
        project_state["phase"] = "readiness_blocked"
    elif gate == "G4" and status in G4_COMPLETION_STATUSES:
        project_state["phase"] = "completed"
    project_state["last_updated"] = now

    consume_human_authorization(
        envelope,
        workspace_ai_team=workspace_root.ai_team,
        transaction=transaction,
    )

    decisions_dir = workspace_root.ai_team / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    decision_path = decisions_dir / f"{gate_decision_id}.yaml"
    transaction.plan_yaml_write(decision_path, decision)
    transaction.plan_yaml_write(state_path, project_state)

    affected: list[dict[str, Any]] = [
        {"kind": "gate_decision", "id": gate_decision_id, "gate": gate, "status": status},
        {"kind": "project_state", "phase": project_state.get("phase")},
    ]

    if gate == "G4" and work_unit_ids:
        human_acceptance_value = HUMAN_ACCEPTANCE_BY_GATE_STATUS.get(status, status)
        wu_dir = workspace_root.ai_team / "work-units"
        for work_unit_id in work_unit_ids:
            wu_path, ambiguity = find_work_unit_path(wu_dir, work_unit_id)
            if ambiguity or wu_path is None:
                continue
            work_unit = yaml.safe_load(wu_path.read_text(encoding="utf-8")) or {}
            work_unit.setdefault("outcomes", {})["human_acceptance"] = human_acceptance_value
            remaining, _cleared = [], []
            for item in work_unit["outcomes"].get("critical_open_items") or []:
                text = str(item).lower()
                if (
                    "human_acceptance" in text
                    or "human acceptance" in text
                    or re.search(r"\bg4\b", text)
                ):
                    _cleared.append(item)
                else:
                    remaining.append(item)
            work_unit["outcomes"]["critical_open_items"] = remaining
            transaction.plan_yaml_write(wu_path, work_unit)
            affected.append(
                {
                    "kind": "work_unit",
                    "id": work_unit_id,
                    "human_acceptance": human_acceptance_value,
                }
            )

    result: dict[str, Any] = {"affected": affected}
    if preconditions_verified:
        result["details"] = {"preconditions_verified": preconditions_verified}
    return result, []
