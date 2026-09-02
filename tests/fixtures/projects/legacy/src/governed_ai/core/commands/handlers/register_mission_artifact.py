"""RegisterMissionArtifact command handler (Document 6 §6.1)."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run.mission_artifact import (
    MISSION_ARTIFACT_KINDS,
    missing_content_fields,
)
from governed_ai.core.persistence.transaction import Transaction


def handle_register_mission_artifact(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    artifact_id = target["id"]
    payload = envelope["payload"]
    kind = payload["kind"]

    if kind not in MISSION_ARTIFACT_KINDS:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"unknown mission artifact kind {kind!r}",
            "/payload/kind",
        )

    artifact_path = workspace_root.ai_team / "mission-artifacts" / f"{artifact_id}.json"
    if artifact_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"mission artifact {artifact_id!r} already exists",
            "/target/id",
        )

    content = payload["content"]
    missing = missing_content_fields(kind, content)
    if missing:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"mission artifact {kind!r} is missing required content fields: {missing}",
            "/payload/content",
        )

    now = datetime.now(UTC).isoformat()
    document = {
        "id": artifact_id,
        "kind": kind,
        "revision": 1,
        # Never trust a client-supplied author — the actor issuing the
        # command is the author, so §6.2's author/reviewer separation cannot
        # be spoofed by naming a different role in the payload.
        "authored_by_role": envelope["actor"]["role_id"],
        "content": content,
        "challenge_status": "pending",
        "challenged_by_role": None,
        "challenged_at": None,
        "challenge_findings": [],
        "created_at": now,
        "updated_at": now,
    }
    validate_against_schema(
        workspace_root.ai_team, document, "mission-artifact.schema.json", root_path=""
    )
    transaction.plan_json_write(artifact_path, document)

    return {
        "affected": [{"kind": "mission_artifact", "id": artifact_id, "revision": 1}],
    }, []
