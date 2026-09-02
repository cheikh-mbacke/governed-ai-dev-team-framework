"""RunAuthorizationGrant mechanical enforcement (Document 6 §8).

Runs the same choke point as role authorization: called from
`authorize_command()` before any handler executes, so no Run-scoped command
can bypass it. `OpenRun` must carry an explicit grant reference (the Run does
not exist yet); every later Run-scoped command is checked against the grant
already bound to that Run at open time — never a freshly supplied one.
"""

from __future__ import annotations

import json
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.domain.run.authorization_grant import unusable_reason

PROTECTED_ENVIRONMENTS = frozenset({"staging", "production"})

REQUIRED_UNATTENDED_COMMANDS = frozenset(
    {
        "OpenRun",
        "AcquireWorkerLease",
        "RecordExecutionAttempt",
        "WriteCheckpoint",
        "CloseRun",
        "ResolveRunDecision",
        "TightenExecutionCeiling",
        "EscalateWorkUnitRisk",
        "RecordWorkerHeartbeat",
        "ReleaseWorkerLease",
        "TransitionWorkUnit",
    }
)

RUN_SCOPED_COMMANDS = frozenset(
    {
        "OpenRun",
        "AcquireWorkerLease",
        "RecordExecutionAttempt",
        "WriteCheckpoint",
        "CloseRun",
        "ResolveRunDecision",
        "TightenExecutionCeiling",
        "EscalateWorkUnitRisk",
        "RecordIntegrationMerge",
        "RecordWorkerHeartbeat",
        "ReleaseWorkerLease",
        "TransitionWorkUnit",
        "RegisterReleaseCandidate",
    }
)

# Commands whose envelope carries the run id on `target.id` rather than `payload.run_id`.
TARGET_IS_RUN_ID_COMMANDS = frozenset(
    {"CloseRun", "TightenExecutionCeiling", "EscalateWorkUnitRisk"}
)


def _grant_path(workspace_ai_team: Path, grant_id: str) -> Path:
    return workspace_ai_team / "run-authorization-grants" / f"{grant_id}.json"


def _load_grant(workspace_ai_team: Path, grant_id: str) -> dict[str, Any] | None:
    path = _grant_path(workspace_ai_team, grant_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _authorize_open_run(envelope: dict[str, Any], workspace_ai_team: Path, *, now_iso: str) -> None:
    grant_id = (envelope.get("run_authorization") or {}).get("grant_id")
    grant = _load_grant(workspace_ai_team, grant_id)
    if grant is None:
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"run authorization grant {grant_id!r} not found",
            "/run_authorization/grant_id",
        )
    reason = unusable_reason(grant, now_iso=now_iso, command_type="OpenRun")
    if reason is not None:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"run authorization grant {grant_id!r} is {reason}",
            "/run_authorization/grant_id",
        )
    if grant.get("uses_count", 0) >= grant.get("maximum_uses", 1):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"run authorization grant {grant_id!r} has no uses remaining",
            "/run_authorization/grant_id",
        )
    work_unit_ids = set((envelope.get("payload") or {}).get("work_unit_ids") or [])
    granted_ids = set(grant.get("work_unit_ids") or [])
    uncovered = sorted(work_unit_ids - granted_ids)
    if uncovered:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"work units not covered by grant {grant_id!r}: {uncovered}",
            "/payload/work_unit_ids",
        )


def _authorize_existing_run_command(
    envelope: dict[str, Any], workspace_ai_team: Path, *, now_iso: str
) -> None:
    command_type = envelope["type"]
    payload = envelope.get("payload") or {}
    run_id = (
        envelope["target"]["id"]
        if command_type in TARGET_IS_RUN_ID_COMMANDS
        else payload.get("run_id")
    )
    if not run_id:
        return
    run_path = workspace_ai_team / "runs" / f"{run_id}.yaml"
    if not run_path.is_file():
        return
    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    grant_id = run_document.get("run_authorization_grant_id")
    if not grant_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"run {run_id!r} has no bound run authorization grant",
            "/payload/run_id",
        )
    grant = _load_grant(workspace_ai_team, grant_id)
    if grant is None:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"bound run authorization grant {grant_id!r} not found",
            "/payload/run_id",
        )
    reason = unusable_reason(grant, now_iso=now_iso, command_type=command_type)
    emergency_close = command_type == "CloseRun" and payload.get("status") in {
        "stopped",
        "failed",
    }
    if reason is not None:
        # Revocation and budget expiry are kill-switch inputs. The reliability
        # controller must still be able to persist the terminal Run state; it
        # may not perform any other action under the unusable grant.
        if emergency_close:
            return
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"run authorization grant {grant_id!r} is {reason}",
            "/payload/run_id",
        )

    allowed_commands = set(grant.get("allowed_commands") or [])
    if allowed_commands and command_type not in allowed_commands:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"command {command_type!r} is outside grant {grant_id!r}",
            "/type",
        )

    environment = payload.get("environment")
    if environment:
        allowed_environments = set(grant.get("allowed_environments") or [])
        if environment in PROTECTED_ENVIRONMENTS or environment not in allowed_environments:
            raise GatewayError(
                ErrorCode.UNAUTHORIZED,
                f"environment {environment!r} is outside grant {grant_id!r}",
                "/payload/environment",
            )

    work_unit_id = payload.get("work_unit_id")
    if work_unit_id and work_unit_id not in set(grant.get("work_unit_ids") or []):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"work unit {work_unit_id!r} is outside grant {grant_id!r}",
            "/payload/work_unit_id",
        )

    maximum_duration_hours = grant.get("maximum_duration_hours")
    if maximum_duration_hours is not None:
        opened_at = run_document.get("created_at")
        if opened_at:
            opened = datetime.fromisoformat(opened_at)
            now = datetime.fromisoformat(now_iso)
            if (now - opened).total_seconds() >= float(maximum_duration_hours) * 3600:
                if emergency_close:
                    return
                raise GatewayError(
                    ErrorCode.UNAUTHORIZED,
                    f"run {run_id!r} exceeded its maximum duration",
                    "/payload/run_id",
                )

    maximum_spend = grant.get("maximum_spend")
    if maximum_spend is not None and float(grant.get("spend_used", 0)) >= float(maximum_spend):
        if emergency_close:
            return
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"run {run_id!r} exhausted its spend budget",
            "/payload/run_id",
        )
    maximum_tokens = grant.get("maximum_tokens")
    if maximum_tokens is not None and int(grant.get("tokens_used", 0)) >= int(maximum_tokens):
        if emergency_close:
            return
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"run {run_id!r} exhausted its token budget",
            "/payload/run_id",
        )


def authorize_run_grant(envelope: dict[str, Any], workspace_ai_team: Path) -> None:
    command_type = envelope["type"]
    if command_type not in RUN_SCOPED_COMMANDS:
        return

    now_iso = datetime.now(UTC).isoformat()
    if command_type == "OpenRun":
        _authorize_open_run(envelope, workspace_ai_team, now_iso=now_iso)
    else:
        _authorize_existing_run_command(envelope, workspace_ai_team, now_iso=now_iso)
