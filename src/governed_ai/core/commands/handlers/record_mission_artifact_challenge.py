"""RecordMissionArtifactChallenge command handler (Document 6 §6.2).

The independent adversarial review a mission artifact must survive before it
can back a RunAuthorizationGrant. The mechanical guarantee this enforces:
whoever authored the artifact can never be the one who approves it — the Core
checks this from the envelope's own actor identity, never from a claim in the
payload.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.domain.run.mission_artifact import CHALLENGE_OUTCOMES, can_challenge
from governed_ai.core.persistence.transaction import Transaction


def handle_record_mission_artifact_challenge(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    artifact_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    outcome = payload["outcome"]

    if outcome not in CHALLENGE_OUTCOMES:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"payload.outcome must be one of {sorted(CHALLENGE_OUTCOMES)}",
            "/payload/outcome",
        )

    artifact_path = workspace_root.ai_team / "mission-artifacts" / f"{artifact_id}.json"
    if not artifact_path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"mission artifact {artifact_id!r} not found",
            "/target/id",
        )
    document = json.loads(artifact_path.read_text(encoding="utf-8"))

    current_revision = document.get("revision", 1)
    if expected_revision != current_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current_revision}",
            "/target/expected_revision",
        )

    challenger_role = envelope["actor"]["role_id"]
    if not can_challenge(
        authored_by_role=document["authored_by_role"], challenger_role=challenger_role
    ):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"role {challenger_role!r} authored this artifact and cannot challenge it",
            "/actor/role_id",
        )

    document["challenge_status"] = outcome
    document["challenged_by_role"] = challenger_role
    document["challenged_at"] = datetime.now(UTC).isoformat()
    document["challenge_findings"] = payload.get("findings", [])
    document["updated_at"] = document["challenged_at"]
    document["revision"] = current_revision + 1
    transaction.plan_json_write(artifact_path, document)

    return {
        "affected": [
            {"kind": "mission_artifact", "id": artifact_id, "revision": document["revision"]},
        ],
    }, []
