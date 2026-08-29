"""TransitionWorkUnit command handler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "ready": frozenset({"in_progress"}),
    "in_progress": frozenset({"verification", "ready"}),
    "verification": frozenset({"done", "in_progress"}),
}


def _current_revision(document: dict[str, Any]) -> int:
    revision = document.get("revision", 1)
    if not isinstance(revision, int):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "revision must be integer", "/revision")
    return revision


def handle_transition_work_unit(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    work_unit_id = target["id"]
    expected_revision = target["expected_revision"]
    to_status = envelope["payload"]["to_status"]

    work_unit_path = workspace_root.ai_team / "work-units" / f"{work_unit_id}.yaml"
    if not work_unit_path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"work unit {work_unit_id!r} not found",
            "/target/id",
        )

    document = yaml.safe_load(work_unit_path.read_text(encoding="utf-8"))
    if document.get("id") != work_unit_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "work unit id mismatch",
            "/target/id",
        )

    current_revision = _current_revision(document)
    if expected_revision != current_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current_revision}",
            "/target/expected_revision",
        )

    current_status = document.get("status")
    allowed = ALLOWED_TRANSITIONS.get(current_status, frozenset())
    if to_status not in allowed:
        raise GatewayError(
            ErrorCode.INVALID_TRANSITION,
            f"transition {current_status!r} -> {to_status!r} not allowed",
            "/payload/to_status",
        )

    document["status"] = to_status
    document["revision"] = current_revision + 1
    document["updated_at"] = datetime.now(UTC).isoformat()
    transaction.plan_yaml_write(work_unit_path, document)

    affected = [
        {
            "kind": "work_unit",
            "id": work_unit_id,
            "revision": document["revision"],
            "status": to_status,
        }
    ]
    return {"affected": affected}, []
