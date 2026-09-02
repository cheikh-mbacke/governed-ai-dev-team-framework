"""RegisterFinding command handler."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.work_unit.paths import find_work_unit_path
from governed_ai.core.persistence.transaction import Transaction


def handle_register_finding(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    finding_id = payload.get("id")
    if not finding_id or not isinstance(finding_id, str):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.id is required", "/payload/id")

    if envelope["target"].get("id") != finding_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )

    work_unit_id = payload.get("work_unit")
    if work_unit_id:
        path, ambiguity = find_work_unit_path(workspace_root.ai_team / "work-units", work_unit_id)
        if ambiguity:
            raise GatewayError(ErrorCode.INVALID_SCHEMA, ambiguity, "/payload/work_unit")
        if path is None:
            raise GatewayError(
                ErrorCode.NOT_FOUND,
                f"work unit {work_unit_id!r} not found",
                "/payload/work_unit",
            )

    finding_path = workspace_root.ai_team / "findings" / f"{finding_id}.yaml"
    if finding_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"finding {finding_id!r} already exists",
            "/payload/id",
        )

    document = dict(payload)
    document.setdefault("status", "open")
    document.setdefault("remediation_required", False)
    now = datetime.now(UTC).isoformat()
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now

    validate_against_schema(
        workspace_root.ai_team,
        document,
        "finding.schema.json",
        root_path="",
    )

    finding_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.plan_yaml_write(finding_path, document)

    affected = [{"kind": "finding", "id": finding_id, "status": document["status"]}]
    if work_unit_id:
        work_unit = yaml.safe_load(path.read_text(encoding="utf-8"))
        outcomes = work_unit.setdefault("outcomes", {})
        audit_findings = outcomes.setdefault("audit_findings", [])
        if finding_id not in audit_findings:
            audit_findings.append(finding_id)
            transaction.plan_yaml_write(path, work_unit)
        affected.append({"kind": "work_unit", "id": work_unit_id, "referenced_finding": finding_id})

    return {"affected": affected}, []
