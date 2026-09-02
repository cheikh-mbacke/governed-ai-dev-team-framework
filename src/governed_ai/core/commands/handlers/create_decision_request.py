"""CreateDecisionRequest command handler."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.persistence.transaction import Transaction


def handle_create_decision_request(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    decision_id = target["id"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    if payload.get("id") != decision_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )

    decision_path = workspace_root.ai_team / "decisions" / f"{decision_id}.yaml"
    if decision_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"decision request {decision_id!r} already exists",
            "/target/id",
        )

    now = datetime.now(UTC).isoformat()
    document = dict(payload)
    document["id"] = decision_id
    document["status"] = "pending_human"
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now
    document.pop("decision", None)

    validate_against_schema(
        workspace_root.ai_team,
        document,
        "decision.schema.json",
        root_path="",
    )

    decision_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.plan_yaml_write(decision_path, document)
    return {
        "affected": [
            {
                "kind": "decision_request",
                "id": decision_id,
                "revision": 1,
                "status": "pending_human",
            }
        ],
    }, []
