"""ReconcileHumanFeedback command handler."""

from __future__ import annotations

from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.work_unit.paths import find_work_unit_path
from governed_ai.core.domain.work_unit.revision import RevisionError, current_revision
from governed_ai.core.persistence.transaction import Transaction

TERMINAL_STATUSES = frozenset({"reconciled", "needs_decision", "superseded"})
CHANGE_CLASSIFICATIONS = frozenset({"defect", "ux_adjustment", "product_intent_change"})


def _validate_action_refs(workspace_root, reconciliation: dict[str, Any]) -> None:
    for work_unit_id in reconciliation.get("affected_work_units") or []:
        path, ambiguity = find_work_unit_path(
            workspace_root.ai_team / "work-units", work_unit_id
        )
        if ambiguity:
            raise GatewayError(ErrorCode.INVALID_SCHEMA, ambiguity, "/payload/reconciliation")
        if path is None:
            raise GatewayError(
                ErrorCode.NOT_FOUND,
                f"affected work unit {work_unit_id!r} not found",
                "/payload/reconciliation/affected_work_units",
            )

    for action in reconciliation.get("actions") or []:
        kind = action.get("kind")
        ref = action.get("ref")
        if kind == "none":
            if ref is not None:
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA,
                    "an action of kind 'none' must have a null ref",
                    "/payload/reconciliation/actions",
                )
            continue
        if not ref:
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"action {kind!r} requires a ref",
                "/payload/reconciliation/actions",
            )
        if kind in {"context_refresh", "reverify_work_unit", "remediation_work_unit"}:
            path, ambiguity = find_work_unit_path(workspace_root.ai_team / "work-units", ref)
            if ambiguity:
                raise GatewayError(ErrorCode.INVALID_SCHEMA, ambiguity, "/payload/reconciliation")
            if path is None:
                raise GatewayError(
                    ErrorCode.NOT_FOUND,
                    f"action references missing work unit {ref!r}",
                    "/payload/reconciliation/actions",
                )
        elif kind == "decision_request":
            if not (workspace_root.ai_team / "decisions" / f"{ref}.yaml").is_file():
                raise GatewayError(
                    ErrorCode.NOT_FOUND,
                    f"action references missing decision request {ref!r}",
                    "/payload/reconciliation/actions",
                )


def handle_reconcile_human_feedback(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    feedback_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    to_status = payload.get("to_status")
    reconciliation = payload.get("reconciliation")

    if to_status not in TERMINAL_STATUSES:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.to_status must be reconciled, needs_decision or superseded",
            "/payload/to_status",
        )
    if not isinstance(reconciliation, dict):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.reconciliation is required",
            "/payload/reconciliation",
        )

    feedback_path = workspace_root.ai_team / "human-feedback" / f"{feedback_id}.yaml"
    if not feedback_path.is_file():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"human feedback {feedback_id!r} not found",
            "/target/id",
        )
    document = yaml.safe_load(feedback_path.read_text(encoding="utf-8")) or {}
    try:
        revision = current_revision(document)
    except RevisionError as exc:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, str(exc), "/revision") from exc
    if revision != expected_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {revision}",
            "/target/expected_revision",
        )
    if document.get("status") != "pending_reconciliation":
        raise GatewayError(
            ErrorCode.INVALID_TRANSITION,
            f"human feedback in status {document.get('status')!r} cannot be reconciled again",
            "/payload/to_status",
        )

    classification = reconciliation.get("classification")
    applicability = reconciliation.get("applicability")
    actions = reconciliation.get("actions") or []
    has_effective_action = any(action.get("kind") != "none" for action in actions)
    if (
        applicability == "applicable"
        and classification in CHANGE_CLASSIFICATIONS
        and not has_effective_action
    ):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "applicable feedback that changes the product requires at least one traced action",
            "/payload/reconciliation/actions",
        )
    if to_status == "needs_decision" and not any(
        action.get("kind") == "decision_request" for action in actions
    ):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "needs_decision requires a decision_request action",
            "/payload/reconciliation/actions",
        )
    _validate_action_refs(workspace_root, reconciliation)

    now = datetime.now(UTC).isoformat()
    reconciled = dict(reconciliation)
    reconciled["reconciled_by_role"] = envelope["actor"]["role_id"]
    reconciled["reconciled_at"] = now
    document["status"] = to_status
    document["reconciliation"] = reconciled
    document["revision"] = revision + 1
    document["updated_at"] = now
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "human-feedback.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(feedback_path, document)

    return {
        "affected": [
            {
                "kind": "human_feedback",
                "id": feedback_id,
                "revision": document["revision"],
                "status": to_status,
            }
        ],
        "details": {
            "affected_work_units": reconciled.get("affected_work_units") or [],
            "invalidated_evidence": reconciled.get("invalidated_evidence") or [],
            "actions": actions,
        },
    }, []
