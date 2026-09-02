"""TightenExecutionCeiling command handler (Document 6 §7.3).

Escalation ("risque découvert plus élevé que prévu") is automatic and
immediate, with no human validation required — an agent can protect itself
by tightening. There is no corresponding "loosen" command anywhere in this
codebase: de-escalation during a run is made structurally impossible here,
not merely discouraged.
"""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run.execution_ceiling import (
    CEILING_DIMENSIONS,
    CEILING_STATES,
    can_tighten,
)
from governed_ai.core.persistence.transaction import Transaction


def handle_tighten_execution_ceiling(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    run_id = target["id"]
    expected_revision = target["expected_revision"]
    payload = envelope["payload"]
    work_unit_id = payload["work_unit_id"]
    dimension = payload["dimension"]
    new_state = payload["new_state"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/target/id")
    document = yaml.safe_load(run_path.read_text(encoding="utf-8"))

    current_revision = document.get("revision", 1)
    if expected_revision != current_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected_revision}, found {current_revision}",
            "/target/expected_revision",
        )

    if dimension not in CEILING_DIMENSIONS:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"unknown execution_ceiling dimension {dimension!r}",
            "/payload/dimension",
        )
    if new_state not in CEILING_STATES:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            f"unknown execution_ceiling state {new_state!r}",
            "/payload/new_state",
        )

    ceilings = document.get("execution_ceilings_by_work_unit") or {}
    ceiling = ceilings.get(work_unit_id)
    if ceiling is None:
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"work unit {work_unit_id!r} has no execution_ceiling on run {run_id!r}",
            "/payload/work_unit_id",
        )

    current_state = ceiling[dimension]
    if not can_tighten(current_state, new_state):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"cannot move execution_ceiling.{dimension} from {current_state!r} to "
            f"{new_state!r}: only strict tightening is allowed during a run",
            "/payload/new_state",
        )

    ceiling[dimension] = new_state
    document["revision"] = current_revision + 1
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    document["updated_at"] = now_iso
    transaction.plan_yaml_write(run_path, document)

    # Document 6 §13 — the morning report must be able to list every escalation
    # and its justification; the mutated ceiling alone has no history of its own.
    escalation_id = f"ESCALATION-{now:%Y%m%dT%H%M%SZ}-{work_unit_id}-{dimension}"
    escalation_path = workspace_root.ai_team / "runs" / "escalations" / f"{escalation_id}.yaml"
    escalation_document = {
        "id": escalation_id,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "dimension": dimension,
        "previous_state": current_state,
        "new_state": new_state,
        "reason": payload["reason"],
        "escalated_at": now_iso,
    }
    validate_against_schema(
        workspace_root.ai_team,
        escalation_document,
        "execution-ceiling-escalation.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(escalation_path, escalation_document)

    return {
        "affected": [
            {"kind": "run", "id": run_id, "revision": document["revision"]},
        ],
        "details": {
            "work_unit_id": work_unit_id,
            "dimension": dimension,
            "previous_state": current_state,
            "new_state": new_state,
            "reason": payload["reason"],
        },
    }, [escalation_id]
