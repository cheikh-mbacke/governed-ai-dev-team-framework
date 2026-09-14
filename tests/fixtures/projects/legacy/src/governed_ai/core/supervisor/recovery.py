"""Bounded recovery for unattended Runs — authoritative mutations via CommandGateway."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.run.autonomy_policy import is_unattended_preset
from governed_ai.core.orchestrator.progress import evaluate_run_progress
from governed_ai.core.supervisor.hard_stops import HARD_STOPS, RECOVERABLE_STOPS
from governed_ai.core.workspace import Workspace
from governed_ai.notifications.service import dispatch_notifications


def _actor() -> dict[str, str]:
    return {
        "kind": "role",
        "execution_id": f"EXE-night-recovery-{uuid.uuid4().hex[:8]}",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "core-supervisor",
    }


def _envelope(command_type: str, *, target: dict, payload: dict, run_id: str) -> dict:
    token = uuid.uuid4().hex
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-night-recovery-{token}",
        "idempotency_key": f"idem-night-recovery-{token}",
        "correlation_id": run_id,
        "type": command_type,
        "issued_at": datetime.now(UTC).isoformat(),
        "actor": _actor(),
        "target": target,
        "payload": payload,
    }


def _read_yaml(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError(f"expected mapping in {path}")
    return document


def _state_path(workspace: Workspace, source_run_id: str) -> Path:
    return workspace.ai_team / "runs" / "recovery" / f"{source_run_id}.json"


def _write_state(workspace: Workspace, source_run_id: str, document: dict) -> None:
    path = _state_path(workspace, source_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    temporary.replace(path)


def _release_active_leases(
    gateway: CommandGateway, workspace: Workspace, run_document: dict
) -> list[str]:
    errors: list[str] = []
    run_id = str(run_document["id"])
    for work_unit_id, lease_ref in (run_document.get("leases_by_work_unit") or {}).items():
        receipt, exit_code = gateway.execute_command(
            _envelope(
                "ReleaseWorkerLease",
                target={"kind": "worker_lease", "id": lease_ref["lease_id"]},
                payload={
                    "run_id": run_id,
                    "work_unit_id": work_unit_id,
                    "epoch": lease_ref["epoch"],
                    "reason": "night recovery fencing after orchestrator failure",
                },
                run_id=run_id,
            )
        )
        if exit_code != 0:
            errors.extend(str(item) for item in receipt.get("errors") or [])
    return errors


def _close_active_run(
    gateway: CommandGateway,
    run_document: dict,
    *,
    stop_condition: str,
    reason: str,
) -> tuple[bool, list]:
    receipt, exit_code = gateway.execute_command(
        _envelope(
            "CloseRun",
            target={
                "kind": "run",
                "id": run_document["id"],
                "expected_revision": run_document["revision"],
            },
            payload={
                "status": "failed",
                "reason": reason,
                "stop_condition": stop_condition,
            },
            run_id=str(run_document["id"]),
        )
    )
    return exit_code == 0, list(receipt.get("errors") or [])


def _reset_recoverable_work_units(
    gateway: CommandGateway, workspace: Workspace, source_run: dict
) -> list[str]:
    errors: list[str] = []
    for work_unit_id in source_run.get("work_unit_ids") or []:
        path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
        try:
            work_unit = _read_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{work_unit_id}: {exc}")
            continue
        if work_unit.get("status") not in {"in_progress", "blocked"}:
            continue
        receipt, exit_code = gateway.execute_command(
            _envelope(
                "TransitionWorkUnit",
                target={
                    "kind": "work_unit",
                    "id": work_unit_id,
                    "expected_revision": work_unit["revision"],
                },
                payload={
                    "run_id": source_run["id"],
                    "to_status": "ready",
                    "reason": "bounded night recovery reset",
                },
                run_id=str(source_run["id"]),
            )
        )
        if exit_code != 0:
            errors.extend(str(item) for item in receipt.get("errors") or [])
    return errors


def boundary_recovery_start_shas(
    workspace: Workspace, source_run_id: str
) -> dict[str, str]:
    """Map work units to the pre-violation base SHA recorded on boundary attempts.

    Used so out-of-scope writes are not carried into a recovery Run (DAEMON-AC-07).
    """
    attempts_dir = workspace.ai_team / "runs" / "execution-attempts"
    selected: dict[str, tuple[str, str]] = {}
    if not attempts_dir.is_dir():
        return {}
    for path in sorted(attempts_dir.glob("*.yaml")):
        try:
            attempt = _read_yaml(path)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        if attempt.get("run_id") != source_run_id:
            continue
        if "Execution boundary:" not in str(attempt.get("summary") or ""):
            continue
        work_unit_id = str(attempt.get("work_unit_id") or "")
        base_sha = str((attempt.get("workspace") or {}).get("base_sha") or "").lower()
        if not work_unit_id or re.fullmatch(r"[0-9a-f]{40}", base_sha) is None:
            continue
        ended_at = str(attempt.get("ended_at") or "")
        if work_unit_id not in selected or ended_at >= selected[work_unit_id][0]:
            selected[work_unit_id] = (ended_at, base_sha)
    return {work_unit_id: value[1] for work_unit_id, value in selected.items()}


def grant_has_remaining_use(workspace: Workspace, grant_id: str | None) -> tuple[bool, str]:
    """Preflight check before OpenRun — gateway remains authoritative."""
    if not grant_id:
        return False, "missing run authorization grant"
    path = workspace.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    if not path.is_file():
        return False, "grant file missing"
    try:
        grant = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"grant unreadable: {exc}"
    if grant.get("status") in {"revoked", "expired", "exhausted"}:
        return False, f"grant status={grant.get('status')}"
    expires_at = grant.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= datetime.now(UTC):
                return False, "grant expired"
        except ValueError:
            return False, "grant expires_at invalid"
    max_uses = grant.get("max_uses")
    uses = int(grant.get("uses_count") or 0)
    if max_uses is not None and uses >= int(max_uses):
        return False, "grant uses exhausted"
    return True, "ok"


def _open_recovery_run(
    gateway: CommandGateway,
    source_run: dict,
    *,
    recovery_number: int,
    recovery_root_run_id: str,
    recovery_start_shas: dict[str, str],
) -> tuple[str | None, list]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    new_run_id = f"RUN-RECOVERY-{stamp}-{recovery_number}"
    payload: dict[str, Any] = {
        "id": new_run_id,
        "opened_by": "night-recovery-controller",
        "work_unit_ids": list(source_run.get("work_unit_ids") or []),
        "status": "active",
        "preflight": dict(source_run.get("preflight") or {}),
        "execution_ceilings_by_work_unit": dict(
            source_run.get("execution_ceilings_by_work_unit") or {}
        ),
        "maximum_parallel_workers": int(source_run.get("maximum_parallel_workers", 1)),
        "maximum_attempts_per_step": int(source_run.get("maximum_attempts_per_step", 3)),
        "maximum_remediation_cycles": int(source_run.get("maximum_remediation_cycles", 2)),
        "autonomy_preset": source_run.get("autonomy_preset"),
        "recovery_root_run_id": recovery_root_run_id,
        "recovery_attempt_number": recovery_number,
    }
    if recovery_start_shas:
        payload["recovery_start_shas_by_work_unit"] = recovery_start_shas
    envelope = _envelope(
        "OpenRun",
        target={"kind": "run", "id": new_run_id},
        payload=payload,
        run_id=new_run_id,
    )
    envelope["run_authorization"] = {"grant_id": source_run["run_authorization_grant_id"]}
    receipt, exit_code = gateway.execute_command(envelope)
    return (new_run_id if exit_code == 0 else None), list(receipt.get("errors") or [])


def _record_recovery_observation(
    gateway: CommandGateway,
    *,
    source_run_id: str,
    outcome: str,
    new_run_id: str | None,
) -> None:
    observation_id = (
        f"OBS-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-NIGHT-RECOVERY-{uuid.uuid4().hex[:6]}"
    )
    gateway.execute_command(
        _envelope(
            "RecordObservation",
            target={"kind": "observation", "id": observation_id},
            payload={
                "id": observation_id,
                "category": "orchestration",
                "severity": "high",
                "symptom": (
                    f"Night recovery outcome={outcome} source_run={source_run_id} "
                    f"new_run={new_run_id}"
                ),
                "classification": {"origin": "framework", "confidence": "certain"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": True,
                    "human_intervention": outcome != "recovered",
                    "affected_work_units": [],
                },
                "evidence_refs": [source_run_id, *([new_run_id] if new_run_id else [])],
                "recurrence_key": "night-mode-auto-recovery",
                "recorded_by": "run-reliability-controller",
            },
            run_id=source_run_id,
        )
    )


def launch_orchestrator(root: Path, run_id: str, workers: int) -> subprocess.Popen:
    command = [
        sys.executable,
        str(root / "scripts" / "ai-team" / "orchestrate.py"),
        "--run-id",
        run_id,
        "--workers",
        str(workers),
        "--no-watchdog",
    ]
    environment = dict(os.environ)
    environment["GOVERNED_AI_WATCHDOG_CHILD"] = "1"
    environment["GOVERNED_AI_SUPERVISOR_MANAGED"] = "1"
    kwargs: dict = {
        "cwd": str(root),
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def recover(
    workspace: Workspace,
    run_id: str,
    *,
    max_recoveries: int,
    launch: bool,
    workers: int,
) -> dict:
    source_path = workspace.ai_team / "runs" / f"{run_id}.yaml"
    try:
        source_run = _read_yaml(source_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {"outcome": "needs_human", "run_id": run_id, "reason": str(exc)}
    if not is_unattended_preset(source_run.get("autonomy_preset")):
        return {
            "outcome": "needs_human",
            "run_id": run_id,
            "reason": "automatic recovery is restricted to unattended Runs",
        }

    recovery_root_run_id = str(source_run.get("recovery_root_run_id") or run_id)
    state_path = _state_path(workspace, recovery_root_run_id)
    try:
        prior = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        prior = {"attempts": 0}
    attempt_number = int(prior.get("attempts", 0)) + 1
    if attempt_number > max_recoveries:
        result = {
            "outcome": "abandoned",
            "run_id": run_id,
            "attempts": attempt_number - 1,
            "reason": "bounded recovery limit exhausted",
        }
        _write_state(workspace, recovery_root_run_id, result)
        return result

    gateway = CommandGateway(workspace)
    if source_run.get("status") == "active":
        progress = evaluate_run_progress(workspace.ai_team, source_run)
        stop_condition = (
            "stalled_no_progress"
            if progress["state"] == "stalled_no_progress"
            else "orchestrator_process_failure"
        )
        lease_errors = _release_active_leases(gateway, workspace, source_run)
        source_run = _read_yaml(source_path)
        closed, close_errors = _close_active_run(
            gateway,
            source_run,
            stop_condition=stop_condition,
            reason="external watchdog initiated bounded recovery",
        )
        if not closed:
            result = {
                "outcome": "needs_human",
                "run_id": run_id,
                "attempts": attempt_number,
                "reason": "could not close active Run",
                "errors": [*lease_errors, *close_errors],
            }
            _write_state(workspace, recovery_root_run_id, result)
            return result
        source_run = _read_yaml(source_path)

    stop_condition = str(source_run.get("stop_condition") or "")
    if stop_condition in HARD_STOPS or stop_condition not in RECOVERABLE_STOPS:
        result = {
            "outcome": "needs_human",
            "run_id": run_id,
            "attempts": attempt_number,
            "reason": f"stop condition is not safely recoverable: {stop_condition or 'unknown'}",
        }
        _write_state(workspace, recovery_root_run_id, result)
        _record_recovery_observation(
            gateway, source_run_id=run_id, outcome="needs_human", new_run_id=None
        )
        dispatch_notifications(workspace, include_digest=True)
        return result

    recovery_start_shas: dict[str, str] = {}
    if stop_condition == "out_of_workspace_write":
        recovery_start_shas = boundary_recovery_start_shas(workspace, run_id)
        if not recovery_start_shas:
            result = {
                "outcome": "needs_human",
                "run_id": run_id,
                "attempts": attempt_number,
                "reason": "no trustworthy pre-violation SHA was recorded",
            }
            _write_state(workspace, recovery_root_run_id, result)
            _record_recovery_observation(
                gateway, source_run_id=run_id, outcome="needs_human", new_run_id=None
            )
            dispatch_notifications(workspace, include_digest=True)
            return result

    usable, grant_reason = grant_has_remaining_use(
        workspace, source_run.get("run_authorization_grant_id")
    )
    if not usable:
        result = {
            "outcome": "needs_human",
            "run_id": run_id,
            "attempts": attempt_number,
            "reason": f"grant cannot open recovery Run: {grant_reason}",
        }
        _write_state(workspace, recovery_root_run_id, result)
        _record_recovery_observation(
            gateway, source_run_id=run_id, outcome="needs_human", new_run_id=None
        )
        dispatch_notifications(workspace, include_digest=True)
        return result

    reset_errors = _reset_recoverable_work_units(gateway, workspace, source_run)
    if reset_errors:
        result = {
            "outcome": "needs_human",
            "run_id": run_id,
            "attempts": attempt_number,
            "reason": "work unit reset failed",
            "errors": reset_errors,
        }
        _write_state(workspace, recovery_root_run_id, result)
        return result

    new_run_id, open_errors = _open_recovery_run(
        gateway,
        source_run,
        recovery_number=attempt_number,
        recovery_root_run_id=recovery_root_run_id,
        recovery_start_shas=recovery_start_shas,
    )
    outcome = "recovered" if new_run_id else "needs_human"
    result = {
        "outcome": outcome,
        "run_id": run_id,
        "new_run_id": new_run_id,
        "attempts": attempt_number,
        "reason": "new governed Run opened" if new_run_id else "OpenRun refused",
        "errors": open_errors,
    }
    _write_state(workspace, recovery_root_run_id, result)
    _record_recovery_observation(
        gateway, source_run_id=run_id, outcome=outcome, new_run_id=new_run_id
    )
    dispatch_notifications(workspace, include_digest=True)
    if launch and new_run_id:
        launch_orchestrator(workspace.root, new_run_id, workers)
    return result
