"""Human authorization consumption for gateway commands."""

from __future__ import annotations

import json
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction


def validate_preissued_human_authorization(
    envelope: dict[str, Any], *, workspace_ai_team: Path
) -> dict[str, Any]:
    """Validate a Core-owned, single-use authorization bound to this command."""
    submitted = envelope.get("human_authorization")
    if not isinstance(submitted, dict):
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "pre-issued human authorization required",
            "/human_authorization",
        )
    auth_id = str(submitted.get("authorization_id") or "")
    path = workspace_ai_team / "authorizations" / f"{auth_id}.json"
    if not auth_id or not path.is_file():
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human authorization token is not pre-issued by the Core",
            "/human_authorization/authorization_id",
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "human authorization record is unreadable",
            "/human_authorization/authorization_id",
        ) from exc
    if not isinstance(record, dict) or record.get("authorization_id") != auth_id:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "human authorization identity mismatch",
            "/human_authorization/authorization_id",
        )
    if record.get("consumed_at"):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "human authorization already consumed",
            "/human_authorization/authorization_id",
        )
    actor = record.get("actor")
    if not isinstance(actor, dict) or actor.get("kind") != "human":
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "authorization actor is not a Core-owned human identity",
            "/human_authorization/granted_by",
        )
    granted_by = str(record.get("granted_by") or actor.get("id") or "")
    if not granted_by.startswith("human:") or submitted.get("granted_by") != granted_by:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "submitted granted_by does not match the issued human identity",
            "/human_authorization/granted_by",
        )
    if record.get("command_type") != envelope.get("type"):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "human authorization was issued for another command",
            "/human_authorization/scope",
        )
    target = record.get("target")
    submitted_target = envelope.get("target") or {}
    if not isinstance(target, dict) or any(
        target.get(key) != submitted_target.get(key) for key in ("kind", "id")
    ):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "human authorization was issued for another target",
            "/human_authorization/scope",
        )
    return record


def consume_human_authorization(
    envelope: dict[str, Any],
    *,
    workspace_ai_team: Path,
    transaction: Transaction,
) -> None:
    auth = envelope["human_authorization"]
    auth_id = auth["authorization_id"]
    path = workspace_ai_team / "authorizations" / f"{auth_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
    else:
        record = dict(auth)
    record["consumed_at"] = datetime.now(UTC).isoformat()
    transaction.plan_json_write(path, record)
