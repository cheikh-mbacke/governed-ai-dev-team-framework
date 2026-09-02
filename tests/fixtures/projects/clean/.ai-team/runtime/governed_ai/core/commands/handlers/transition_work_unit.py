"""TransitionWorkUnit command handler."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.domain.work_unit.done import missing_done_prerequisites
from governed_ai.core.domain.work_unit.revision import RevisionError, current_revision
from governed_ai.core.domain.work_unit.state_machine import is_transition_allowed
from governed_ai.core.persistence.transaction import Transaction


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

    try:
        current = current_revision(document)
    except RevisionError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/revision") from exc
    if expected_revision != current:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current}",
            "/target/expected_revision",
        )

    current_status = document.get("status")
    if not is_transition_allowed(current_status, to_status):
        raise GatewayError(
            ErrorCode.INVALID_TRANSITION,
            f"transition {current_status!r} -> {to_status!r} not allowed",
            "/payload/to_status",
        )

    if to_status == "done":
        missing = missing_done_prerequisites(document)
        if missing:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"done prerequisites not satisfied: {', '.join(missing)}",
                "/payload/to_status",
            )

    document["status"] = to_status
    document["revision"] = current + 1
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
