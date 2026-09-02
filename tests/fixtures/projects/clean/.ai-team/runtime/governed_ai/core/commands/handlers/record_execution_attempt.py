"""RecordExecutionAttempt command handler — fencing-checked write (Document 6 §2.6, §9.4)."""

from __future__ import annotations

import json
from governed_ai.compat.datetime import UTC, datetime
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run import fencing
from governed_ai.core.domain.run.convergence import (
    DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP,
    DEFAULT_MAXIMUM_REMEDIATION_CYCLES,
    attempts_for_step,
    convergence_exhaustion_reason,
)
from governed_ai.core.domain.run.execution_ceiling import (
    DEFAULT_EXECUTION_CEILING,
    is_step_permitted,
)
from governed_ai.core.persistence.transaction import Transaction


def _load_run_attempts(workspace_root, run_id: str) -> list[dict[str, Any]]:
    attempts_dir = workspace_root.ai_team / "runs" / "execution-attempts"
    if not attempts_dir.is_dir():
        return []
    attempts = []
    for path in sorted(attempts_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("run_id") == run_id:
            attempts.append(document)
    return attempts


def handle_record_execution_attempt(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    attempt_id = envelope["target"]["id"]
    payload = envelope["payload"]
    run_id = payload["run_id"]
    work_unit_id = payload["work_unit_id"]
    epoch = payload["epoch"]
    step = payload["step"]

    run_path = workspace_root.ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, f"run {run_id!r} not found", "/payload/run_id")
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))

    if (
        run_document.get("autonomy_preset", "supervised_copilots").startswith("unattended_")
        and run_document.get("status") != "active"
    ):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"run {run_id!r} is not active",
            "/payload/run_id",
        )

    if work_unit_id not in (run_document.get("work_unit_ids") or []):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"work unit {work_unit_id!r} is not part of run {run_id!r}",
            "/payload/work_unit_id",
        )

    if not fencing.is_epoch_current(run_document, work_unit_id, epoch):
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"stale worker lease epoch for work unit {work_unit_id!r}",
            "/payload/epoch",
        )

    current_lease = fencing.current_lease(run_document, work_unit_id)
    if current_lease is None or current_lease.get("lease_id") != payload["worker_lease_id"]:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"worker lease id is not current for work unit {work_unit_id!r}",
            "/payload/worker_lease_id",
        )

    attempt_path = workspace_root.ai_team / "runs" / "execution-attempts" / f"{attempt_id}.yaml"
    existing_document = None
    if attempt_path.is_file():
        existing_document = yaml.safe_load(attempt_path.read_text(encoding="utf-8"))
        expected_revision = envelope["target"].get("expected_revision")
        if existing_document.get("status") != "started" or payload["status"] == "started":
            raise GatewayError(
                ErrorCode.ALREADY_EXISTS,
                f"execution attempt {attempt_id!r} is already terminal",
                "/target/id",
            )
        if expected_revision != existing_document.get("revision"):
            raise GatewayError(
                ErrorCode.CONFLICT,
                f"execution attempt {attempt_id!r} revision conflict",
                "/target/expected_revision",
            )
        for field in ("run_id", "work_unit_id", "worker_lease_id", "epoch", "step"):
            if existing_document.get(field) != payload.get(field):
                raise GatewayError(
                    ErrorCode.CONFLICT,
                    f"execution attempt completion changed immutable field {field!r}",
                    f"/payload/{field}",
                )

    # Document 6 §7.1/§15 — an attempt beyond a Work Unit's execution_ceiling is
    # rejected by the Core, not merely discouraged.  The sole conditional path
    # implemented by the reference workflow is an integration review issued by
    # the integration-steward itself (Document 6 §7.1/§10.1).
    ceiling = (run_document.get("execution_ceilings_by_work_unit") or {}).get(
        work_unit_id, DEFAULT_EXECUTION_CEILING
    )
    conditional_authorized = (
        step == "integration_review"
        and envelope["actor"]["role_id"] == "integration-steward"
    )
    permitted, ceiling_state = is_step_permitted(
        ceiling,
        step,
        conditional_authorized=conditional_authorized,
    )
    if not permitted:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"step {step!r} on work unit {work_unit_id!r} is {ceiling_state} under its execution_ceiling",
            "/payload/step",
        )

    # Document 6 §9.3 — bounded convergence loop: mechanical, not agent-judged.
    # A prior attempt already at the bound wrote its own diagnostic alert (below),
    # so refusing this one outright is never a silent rejection.
    maximum_attempts_per_step = run_document.get(
        "maximum_attempts_per_step", DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP
    )
    maximum_remediation_cycles = run_document.get(
        "maximum_remediation_cycles", DEFAULT_MAXIMUM_REMEDIATION_CYCLES
    )
    prior_attempts = attempts_for_step(
        _load_run_attempts(workspace_root, run_id), work_unit_id, step
    )
    if existing_document is not None:
        prior_attempts = [item for item in prior_attempts if item.get("id") != attempt_id]
    if (
        convergence_exhaustion_reason(
            prior_attempts,
            step=step,
            maximum_attempts_per_step=maximum_attempts_per_step,
            maximum_remediation_cycles=maximum_remediation_cycles,
        )
        is not None
    ):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"convergence loop already exhausted for step {step!r} on work unit {work_unit_id!r}",
            "/payload/step",
        )

    now = datetime.now(UTC).isoformat()
    document = {
        "id": attempt_id,
        "revision": (existing_document or {}).get("revision", 0) + 1,
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "worker_lease_id": payload["worker_lease_id"],
        "epoch": epoch,
        "step": step,
        "status": payload["status"],
        "started_at": payload.get("started_at", (existing_document or {}).get("started_at", now)),
        "ended_at": payload.get("ended_at", None if payload["status"] == "started" else now),
        "summary": payload.get("summary"),
        "checks": payload.get("checks", []),
        "artifacts": payload.get("artifacts", []),
        "workspace": payload.get("workspace", {}),
        "contract": payload.get("contract", {}),
        "requested_commands": payload.get("requested_commands", []),
        "usage": payload.get("usage", {}),
    }
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "execution-attempt.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(attempt_path, document)

    domain_events: list[str] = []
    details: dict[str, Any] = {}

    if document["status"] != "started":
        grant_id = run_document["run_authorization_grant_id"]
        grant_path = workspace_root.ai_team / "run-authorization-grants" / f"{grant_id}.json"
        grant_document = json.loads(grant_path.read_text(encoding="utf-8"))
        usage = document.get("usage") or {}
        grant_document["spend_used"] = float(grant_document.get("spend_used", 0)) + float(
            usage.get("cost", 0) or 0
        )
        grant_document["tokens_used"] = int(grant_document.get("tokens_used", 0)) + int(
            usage.get("total_tokens", 0) or 0
        )
        transaction.plan_json_write(grant_path, grant_document)
        spend_exhausted = (
            grant_document.get("maximum_spend") is not None
            and grant_document["spend_used"] >= float(grant_document["maximum_spend"])
        )
        tokens_exhausted = (
            grant_document.get("maximum_tokens") is not None
            and grant_document["tokens_used"] >= int(grant_document["maximum_tokens"])
        )
        if spend_exhausted or tokens_exhausted:
            # Signal the reliability controller. It performs CloseRun as a
            # separate authoritative command so leases are revoked and the
            # mandatory immediate BLOCKER event is persisted atomically.
            details["global_stop_condition"] = "budget_exhausted"
    exhaustion_reason = convergence_exhaustion_reason(
        prior_attempts + ([] if document["status"] == "started" else [document]),
        step=step,
        maximum_attempts_per_step=maximum_attempts_per_step,
        maximum_remediation_cycles=maximum_remediation_cycles,
    )
    if document["status"] != "started" and exhaustion_reason is not None:
        details["convergence_exhausted"] = True
        details["convergence_exhaustion_reason"] = exhaustion_reason
        event_id = f"EVT-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-CONVERGENCE-{work_unit_id}"
        event_path = workspace_root.ai_team / "events" / f"{event_id}.yaml"
        transaction.plan_yaml_write(
            event_path,
            {
                "id": event_id,
                "type": "BLOCKER",
                "work_unit": work_unit_id,
                "created_at": now,
                "created_by_role": "run-reliability-controller",
                "summary": (
                    f"Convergence loop exhausted for step {step!r} on work unit "
                    f"{work_unit_id!r}: {exhaustion_reason}."
                ),
                "details": {
                    "run_id": run_id,
                    "work_unit_id": work_unit_id,
                    "step": step,
                    "reason": exhaustion_reason,
                },
                "affected_nodes": [{"kind": "work_unit", "id": work_unit_id}],
                "requires_human": True,
                "status": "open",
            },
        )
        domain_events.append(event_id)

    return {
        "affected": [
            {
                "kind": "execution_attempt",
                "id": attempt_id,
                "revision": document["revision"],
                "status": document["status"],
            },
        ],
        "details": details or None,
    }, domain_events
