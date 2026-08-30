"""CreateWorkUnit command handler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.persistence.transaction import Transaction


def _default_outcomes() -> dict[str, Any]:
    return {
        "review_status": "pending",
        "audit_status": "not_required",
        "critical_open_items": [],
        "defects": [],
        "audit_findings": [],
        "human_acceptance": None,
    }


def handle_create_work_unit(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    work_unit_id = target["id"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    payload_id = payload.get("id")
    if payload_id != work_unit_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )

    work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
    if work_unit_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"work unit {work_unit_id!r} already exists",
            "/target/id",
        )

    now = datetime.now(UTC).isoformat()
    document = dict(payload)
    document["id"] = work_unit_id
    document.setdefault("status", "draft")
    document.setdefault("events", [])
    document.setdefault("evidence", [])
    document.setdefault("outcomes", _default_outcomes())
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now

    if document["status"] not in {"draft", "ready"}:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "initial status must be draft or ready",
            "/payload/status",
        )

    validate_against_schema(
        workspace_root.ai_team,
        document,
        "work-unit.schema.json",
        root_path="",
    )

    transaction.plan_yaml_write(work_unit_path, document)
    return {
        "affected": [
            {
                "kind": "work_unit",
                "id": work_unit_id,
                "revision": 1,
                "status": document["status"],
            }
        ],
    }, []
