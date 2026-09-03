"""ReviewRetrospective command handler — status-only generated → reviewed."""

from __future__ import annotations

from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace_mode import ensure_feedback_allowed
from governed_ai.feedback import common
from governed_ai.feedback.domain.retrospective import apply_review, revision_of


def handle_review_retrospective(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    ensure_feedback_allowed(workspace_root)

    target = envelope["target"]
    retrospective_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    path = workspace_root.ai_team / "retrospectives" / f"{retrospective_id}.yaml"
    if not path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"retrospective {retrospective_id!r} not found",
            "/target/id",
        )

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("id") != retrospective_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "retrospective id mismatch",
            "/target/id",
        )

    current = revision_of(document)
    if expected_revision != current:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current}",
            "/target/expected_revision",
        )

    try:
        updated = apply_review(
            document,
            reviewed_by=payload.get("reviewed_by"),
            notes=payload.get("notes"),
        )
    except ValueError as exc:
        message = str(exc)
        if "not allowed" in message:
            raise GatewayError(
                ErrorCode.INVALID_TRANSITION,
                message,
                "/payload",
            ) from exc
        raise GatewayError(ErrorCode.INVALID_SCHEMA, message, "/payload") from exc

    try:
        common.validate_payload(workspace_root, updated, "retrospective.schema.json")
    except ValueError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/payload") from exc

    transaction.plan_yaml_write(path, updated)
    return {
        "affected": [
            {
                "kind": "retrospective",
                "id": retrospective_id,
                "revision": updated["revision"],
                "status": updated["status"],
                "from_status": document.get("status"),
            }
        ],
    }, []
