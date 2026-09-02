"""RegisterReleaseCandidate command handler."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.persistence.transaction import Transaction


def handle_register_release_candidate(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    candidate_id = target["id"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    if payload.get("id") != candidate_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )

    candidate_path = workspace_root.ai_team / "release-candidates" / f"{candidate_id}.yaml"
    if candidate_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"release candidate {candidate_id!r} already exists",
            "/target/id",
        )

    document = dict(payload)
    document["id"] = candidate_id
    document.setdefault("status", "draft")
    now = datetime.now(UTC).isoformat()
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now

    validate_against_schema(
        workspace_root.ai_team,
        document,
        "release-candidate.schema.json",
        root_path="",
    )

    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.plan_yaml_write(candidate_path, document)
    return {
        "affected": [
            {
                "kind": "release_candidate",
                "id": candidate_id,
                "status": document["status"],
            }
        ],
    }, []
