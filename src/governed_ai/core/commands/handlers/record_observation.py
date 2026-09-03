"""RecordObservation command handler (mediated port for readonly roles)."""

from __future__ import annotations

from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace_mode import ensure_feedback_allowed
from governed_ai.feedback.commands.handlers import (
    RecordObservationParams,
    prepare_observation_write,
)
from governed_ai.feedback.domain.observation import occurrence_count_of


def handle_record_observation(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")

    ensure_feedback_allowed(workspace_root)

    actor = envelope["actor"]
    params = RecordObservationParams(
        category=str(payload.get("category", "other")),
        symptom=str(payload.get("symptom", "")),
        severity=str(payload.get("severity", "medium")),
        origin=str((payload.get("classification") or {}).get("origin", "unknown")),
        confidence=str((payload.get("classification") or {}).get("confidence", "low")),
        work_unit=payload.get("work_unit"),
        phase=payload.get("phase"),
        recorded_by=payload.get("recorded_by") or actor.get("role_id"),
        observation_id=payload.get("id"),
        blocked_minutes=int((payload.get("impact") or {}).get("blocked_minutes", 0)),
        rework_required=bool((payload.get("impact") or {}).get("rework_required", False)),
        human_intervention=bool(
            (payload.get("impact") or {}).get("human_intervention", False)
        ),
        affected_work_unit=tuple(
            (payload.get("impact") or {}).get("affected_work_units") or ()
        ),
        evidence_ref=tuple(payload.get("evidence_refs") or ()),
        workaround=payload.get("workaround"),
        candidate_improvement=payload.get("candidate_improvement"),
        recurrence_key=payload.get("recurrence_key"),
        status=str(payload.get("status", "open")),
        resolution=payload.get("resolution"),
    )
    if not params.symptom:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.symptom is required", "/payload/symptom")

    try:
        prepared = prepare_observation_write(workspace_root, params)
    except ValueError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/payload") from exc

    path = prepared.path
    document = prepared.document
    if not prepared.coalesced and path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"observation {document['id']!r} already exists",
            "/payload/id",
        )

    transaction.plan_yaml_write(path, document)
    return {
        "affected": [
            {
                "kind": "observation",
                "id": document["id"],
                "coalesced": prepared.coalesced,
                "occurrence_count": occurrence_count_of(document),
            }
        ],
    }, []
