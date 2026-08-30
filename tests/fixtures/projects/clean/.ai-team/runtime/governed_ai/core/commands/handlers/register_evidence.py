"""RegisterEvidence command handler (create-exclusive, CG-011)."""

from __future__ import annotations

from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.persistence.transaction import Transaction


def handle_register_evidence(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    evidence_id = payload.get("id")
    if not evidence_id or not isinstance(evidence_id, str):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.id is required", "/payload/id")

    path = workspace_root.ai_team / "evidence" / f"{evidence_id}.yaml"
    if path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"evidence {evidence_id!r} already exists",
            "/payload/id",
        )

    validate_against_schema(workspace_root.ai_team, payload, "evidence.schema.json")

    transaction.plan_yaml_write(path, payload)
    return {
        "affected": [{"kind": "evidence", "id": evidence_id}],
    }, []
