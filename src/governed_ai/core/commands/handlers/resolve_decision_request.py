"""ResolveDecisionRequest command handler."""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.domain.decisions.option_ids import option_ids
from governed_ai.core.domain.decisions.state_machine import is_transition_allowed
from governed_ai.core.domain.work_unit.revision import RevisionError, current_revision
from governed_ai.core.persistence.transaction import Transaction


def handle_resolve_decision_request(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    decision_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    to_status = payload.get("to_status")
    if to_status not in {"decided", "cancelled"}:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.to_status must be decided or cancelled",
            "/payload/to_status",
        )

    decision_path = workspace_root.ai_team / "decisions" / f"{decision_id}.yaml"
    if not decision_path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"decision request {decision_id!r} not found",
            "/target/id",
        )

    document = yaml.safe_load(decision_path.read_text(encoding="utf-8"))
    if document.get("id") != decision_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "decision id mismatch",
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

    original_question = document.get("question")
    original_options = document.get("options")

    if to_status == "decided":
        decision = payload.get("decision")
        if not isinstance(decision, dict):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                "payload.decision is required when to_status is decided",
                "/payload/decision",
            )
        selected = decision.get("selected_option")
        if not selected:
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                "payload.decision.selected_option is required",
                "/payload/decision/selected_option",
            )
        allowed_options = option_ids(original_options or [])
        if allowed_options and selected not in allowed_options:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"selected_option {selected!r} is not among declared options",
                "/payload/decision/selected_option",
            )
        document["decision"] = decision
    else:
        document.pop("decision", None)
        if payload.get("reason"):
            document["cancellation_reason"] = payload["reason"]

    document["status"] = to_status
    document["question"] = original_question
    document["options"] = original_options
    document["revision"] = current + 1
    document["updated_at"] = datetime.now(UTC).isoformat()

    consume_human_authorization(
        envelope,
        workspace_ai_team=workspace_root.ai_team,
        transaction=transaction,
    )
    transaction.plan_yaml_write(decision_path, document)

    return {
        "affected": [
            {
                "kind": "decision_request",
                "id": decision_id,
                "revision": document["revision"],
                "status": to_status,
            }
        ],
    }, []
