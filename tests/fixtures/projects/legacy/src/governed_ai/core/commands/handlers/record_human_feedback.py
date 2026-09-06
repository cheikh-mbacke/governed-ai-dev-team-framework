"""RecordHumanFeedback command handler.

Human UI feedback is asynchronous product input, not G4 acceptance. Recording it
must therefore never transition a Work Unit, close a Run, or lower an execution
ceiling. It only creates the feedback object, links it to the observed Work Unit,
and closes the informational checkpoint when one was supplied.
"""

from __future__ import annotations

from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.work_unit.paths import find_work_unit_path
from governed_ai.core.domain.work_unit.revision import RevisionError, current_revision
from governed_ai.core.persistence.transaction import Transaction


def _find_checkpoint(events_dir, checkpoint_ref: str):
    direct = events_dir / f"{checkpoint_ref}.yaml"
    candidates = [direct] if direct.is_file() else sorted(events_dir.glob("*.yaml"))
    for path in candidates:
        try:
            event = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if event.get("id") == checkpoint_ref:
            return path, event
    return None, None


def handle_record_human_feedback(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    feedback_id = target["id"]
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    if payload.get("id") != feedback_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )

    feedback_path = workspace_root.ai_team / "human-feedback" / f"{feedback_id}.yaml"
    if feedback_path.is_file():
        raise GatewayError(ErrorCode.ALREADY_EXISTS, f"human feedback {feedback_id!r} already exists")

    granted_by = (envelope.get("human_authorization") or {}).get("granted_by")
    if payload.get("submitted_by") != granted_by:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.submitted_by must match human_authorization.granted_by",
            "/payload/submitted_by",
        )

    work_unit_id = payload.get("work_unit")
    work_unit_path, ambiguity = find_work_unit_path(
        workspace_root.ai_team / "work-units", work_unit_id
    )
    if ambiguity:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, ambiguity, "/payload/work_unit")
    if work_unit_path is None:
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"work unit {work_unit_id!r} not found",
            "/payload/work_unit",
        )

    checkpoint_path = None
    checkpoint = None
    checkpoint_ref = payload.get("checkpoint_ref")
    if checkpoint_ref:
        checkpoint_path, checkpoint = _find_checkpoint(
            workspace_root.ai_team / "events", checkpoint_ref
        )
        if checkpoint_path is None:
            raise GatewayError(
                ErrorCode.NOT_FOUND,
                f"human checkpoint {checkpoint_ref!r} not found",
                "/payload/checkpoint_ref",
            )
        if checkpoint.get("work_unit") != work_unit_id:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "checkpoint and feedback must reference the same work unit",
                "/payload/checkpoint_ref",
            )
        if not ((checkpoint.get("details") or {}).get("human_checkpoint")):
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "referenced event is not a human checkpoint",
                "/payload/checkpoint_ref",
            )
        if checkpoint.get("status") != "open":
            raise GatewayError(
                ErrorCode.INVALID_TRANSITION,
                "referenced human checkpoint is not open",
                "/payload/checkpoint_ref",
            )
        checkpoint_details = checkpoint["details"]["human_checkpoint"]
        observed_sha = (payload.get("observed_revision") or {}).get("commit_sha")
        checkpoint_sha = checkpoint_details.get("observed_revision")
        if checkpoint_sha and observed_sha != checkpoint_sha:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "feedback commit SHA must match the referenced checkpoint",
                "/payload/observed_revision/commit_sha",
            )
        checkpoint_surface = checkpoint_details.get("surface")
        if checkpoint_surface and payload.get("surface") != checkpoint_surface:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "feedback surface must match the referenced checkpoint",
                "/payload/surface",
            )

    now = datetime.now(UTC).isoformat()
    document = dict(payload)
    document["id"] = feedback_id
    document["status"] = "pending_reconciliation"
    document.pop("reconciliation", None)
    document["revision"] = 1
    document["created_at"] = now
    document["updated_at"] = now
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "human-feedback.schema.json",
        root_path="",
    )

    work_unit = yaml.safe_load(work_unit_path.read_text(encoding="utf-8")) or {}
    try:
        work_unit_revision = current_revision(work_unit)
    except RevisionError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/work_unit/revision") from exc
    outcomes = work_unit.setdefault("outcomes", {})
    feedback_refs = outcomes.setdefault("human_feedback", [])
    if feedback_id not in feedback_refs:
        feedback_refs.append(feedback_id)
    work_unit["revision"] = work_unit_revision + 1
    work_unit["updated_at"] = now

    consume_human_authorization(
        envelope,
        workspace_ai_team=workspace_root.ai_team,
        transaction=transaction,
    )
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    transaction.plan_yaml_write(feedback_path, document)
    transaction.plan_yaml_write(work_unit_path, work_unit)

    affected = [
        {
            "kind": "human_feedback",
            "id": feedback_id,
            "revision": 1,
            "status": "pending_reconciliation",
        },
        {
            "kind": "work_unit",
            "id": work_unit_id,
            "revision": work_unit["revision"],
            "status": work_unit.get("status"),
        },
    ]
    if checkpoint_path is not None and checkpoint is not None:
        checkpoint["status"] = "closed"
        details = checkpoint.setdefault("details", {})
        details["human_feedback_ref"] = feedback_id
        transaction.plan_yaml_write(checkpoint_path, checkpoint)
        affected.append({"kind": "event", "id": checkpoint_ref, "status": "closed"})

    return {
        "affected": affected,
        "details": {
            "non_blocking": True,
            "work_unit_status_unchanged": True,
            "next_action": "reconcile human feedback against current project state",
        },
    }, []
