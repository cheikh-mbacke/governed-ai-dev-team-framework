"""RecordAcceptance command handler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.persistence.transaction import Transaction


def handle_record_acceptance(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    acceptance_id = target["id"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    if payload.get("id") != acceptance_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )

    acceptance_path = workspace_root.ai_team / "acceptance" / f"{acceptance_id}.yaml"
    if acceptance_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"acceptance {acceptance_id!r} already exists",
            "/target/id",
        )

    document = dict(payload)
    document["id"] = acceptance_id
    now = datetime.now(UTC).isoformat()
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now

    validate_against_schema(
        workspace_root.ai_team,
        document,
        "acceptance.schema.json",
        root_path="",
    )

    consume_human_authorization(
        envelope,
        workspace_ai_team=workspace_root.ai_team,
        transaction=transaction,
    )

    acceptance_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.plan_yaml_write(acceptance_path, document)
    return {
        "affected": [
            {
                "kind": "acceptance",
                "id": acceptance_id,
                "status": document.get("human_result", {}).get("status"),
            }
        ],
    }, []
