"""RevokeRunAuthorizationGrant command handler (Document 6 §8, feeds the §9.7 kill switch)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.persistence.transaction import Transaction


def handle_revoke_run_authorization_grant(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    grant_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]

    grant_path = workspace_root.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    if not grant_path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"run authorization grant {grant_id!r} not found",
            "/target/id",
        )
    document = json.loads(grant_path.read_text(encoding="utf-8"))

    current_revision = document.get("revision", 1)
    if expected_revision != current_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current_revision}",
            "/target/expected_revision",
        )

    if document.get("revoked_at"):
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"run authorization grant {grant_id!r} already revoked",
            "/target/id",
        )

    document["revoked_at"] = datetime.now(UTC).isoformat()
    document["revoked_reason"] = payload["reason"]
    document["revision"] = current_revision + 1
    transaction.plan_json_write(grant_path, document)
    consume_human_authorization(
        envelope, workspace_ai_team=workspace_root.ai_team, transaction=transaction
    )

    return {
        "affected": [
            {"kind": "run_authorization_grant", "id": grant_id, "revision": document["revision"]},
        ],
    }, []
