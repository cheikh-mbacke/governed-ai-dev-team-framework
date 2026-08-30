"""ResolveRunDecision command handler (Document 6 §5.3-§5.4).

`mandate-matcher` (an agent) proposes a correspondence between an observed
fork and a decision-menu entry on the Run's grant; this handler is the
deterministic Core validator that alone can turn it into an automatic
resolution. No natural-language interpretation happens here — only the
structural checks in `domain.run.decision_menu`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run.decision_menu import validate_entry_usable
from governed_ai.core.persistence.transaction import Transaction


def handle_resolve_run_decision(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    decision_id = envelope["target"]["id"]
    payload = envelope["payload"]
    run_id = payload["run_id"]
    work_unit_id = payload["work_unit_id"]
    trigger = payload["trigger"]
    proposed_entry_id = payload["proposed_entry_id"]
    evidence = payload.get("evidence") or []

    decision_path = workspace_root.ai_team / "runs" / "decisions" / f"{decision_id}.yaml"
    if decision_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"run decision {decision_id!r} already exists",
            "/target/id",
        )

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/payload/run_id")
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))

    grant_id = run_document["run_authorization_grant_id"]
    grant_path = workspace_root.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    grant_document = json.loads(grant_path.read_text(encoding="utf-8"))
    entries = grant_document.get("decision_menu") or []
    entry = next((item for item in entries if item.get("id") == proposed_entry_id), None)
    if work_unit_id not in (run_document.get("work_unit_ids") or []):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"work unit {work_unit_id!r} is not part of run {run_id!r}",
            "/payload/work_unit_id",
        )

    now = datetime.now(UTC).isoformat()
    environment = payload.get("environment")
    reason = (
        "entry_not_found"
        if entry is None
        else validate_entry_usable(
            entry,
            trigger=trigger,
            work_unit_id=work_unit_id,
            environment=environment,
            now_iso=now,
            evidence=evidence,
        )
    )
    resolved = reason is None

    document = {
        "id": decision_id,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "trigger": trigger,
        "proposed_entry_id": proposed_entry_id,
        "evidence": evidence,
        "resolved": resolved,
        "rejection_reason": reason,
        "resolved_at": now,
    }
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "run-decision.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(decision_path, document)

    if resolved:
        assert entry is not None
        entry["uses_count"] = entry.get("uses_count", 0) + 1
        transaction.plan_json_write(grant_path, grant_document)
        # A valid answer supplied after the grouped morning review reopens the
        # paused WU at exactly the interrupted workflow state. The scheduler
        # will acquire a fresh fenced lease before any adapter is launched.
        work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
        if work_unit_path.is_file():
            work_unit = yaml.safe_load(work_unit_path.read_text(encoding="utf-8"))
            if work_unit.get("status") == "waiting_decision":
                work_unit["status"] = "in_progress"
                work_unit["revision"] = work_unit.get("revision", 1) + 1
                work_unit["updated_at"] = now
                transaction.plan_yaml_write(work_unit_path, work_unit)
    else:
        # Document 6 §5.4/§12.2 — an unmatched fork pauses only this Work
        # Unit and therefore its dependent subgraph. Independent ready Work
        # Units remain schedulable.
        work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
        if work_unit_path.is_file():
            work_unit = yaml.safe_load(work_unit_path.read_text(encoding="utf-8"))
            if work_unit.get("status") == "in_progress":
                work_unit["status"] = "waiting_decision"
                work_unit["revision"] = work_unit.get("revision", 1) + 1
                work_unit["updated_at"] = now
                transaction.plan_yaml_write(work_unit_path, work_unit)

        lease_ref = (run_document.get("leases_by_work_unit") or {}).get(work_unit_id)
        if lease_ref:
            lease_path = (
                workspace_root.ai_team / "runs" / "leases" / f"{lease_ref['lease_id']}.yaml"
            )
            if lease_path.is_file():
                lease = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
                lease["status"] = "released"
                lease["released_at"] = now
                lease["release_reason"] = "decision requires human authority"
                transaction.plan_yaml_write(lease_path, lease)
            del run_document["leases_by_work_unit"][work_unit_id]
            run_document["updated_at"] = now
            transaction.plan_yaml_write(run_path, run_document)

    return {
        "affected": [{"kind": "run_decision", "id": decision_id, "resolved": resolved}],
        "details": {"resolved": resolved, "rejection_reason": reason},
    }, []
