"""TransitionObservation command handler — Observation lifecycle."""

from __future__ import annotations

from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace_mode import ensure_feedback_allowed
from governed_ai.feedback import common
from governed_ai.feedback.domain.observation import (
    ALL_STATUSES,
    apply_transition,
    revision_of,
)


def handle_transition_observation(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    ensure_feedback_allowed(workspace_root)

    target = envelope["target"]
    observation_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    to_status = payload.get("to_status")
    if to_status not in ALL_STATUSES:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.to_status must be a valid observation status",
            "/payload/to_status",
        )

    path = workspace_root.ai_team / "observations" / f"{observation_id}.yaml"
    if not path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"observation {observation_id!r} not found",
            "/target/id",
        )

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("id") != observation_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "observation id mismatch",
            "/target/id",
        )

    current = revision_of(document)
    if expected_revision != current:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current}",
            "/target/expected_revision",
        )

    classification = payload.get("classification")
    origin = None
    confidence = None
    if classification is not None:
        if not isinstance(classification, dict):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                "payload.classification must be an object",
                "/payload/classification",
            )
        origin = classification.get("origin")
        confidence = classification.get("confidence")

    try:
        updated = apply_transition(
            document,
            to_status=str(to_status),
            resolution=payload.get("resolution"),
            origin=origin,
            confidence=confidence,
        )
    except ValueError as exc:
        message = str(exc)
        if "not allowed" in message:
            raise GatewayError(
                ErrorCode.INVALID_TRANSITION,
                message,
                "/payload/to_status",
            ) from exc
        raise GatewayError(ErrorCode.INVALID_SCHEMA, message, "/payload") from exc

    try:
        common.validate_payload(workspace_root, updated, "observation.schema.json")
    except ValueError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/payload") from exc

    transaction.plan_yaml_write(path, updated)
    return {
        "affected": [
            {
                "kind": "observation",
                "id": observation_id,
                "revision": updated["revision"],
                "status": updated["status"],
                "from_status": document.get("status"),
            }
        ],
    }, []
