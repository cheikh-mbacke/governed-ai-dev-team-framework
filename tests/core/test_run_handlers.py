"""Mode nuit Étapes 1-5 — Run/WorkerLease/ExecutionAttempt/Checkpoint, fencing,
preflight, global stop conditions, bounded convergence, RunAuthorizationGrant
(Document 6 §8, §9.1-§9.6, §11)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GRANT_ID = "GRANT-DEFAULT"


def _seed_grant(
    workspace: Workspace,
    grant_id: str,
    *,
    work_unit_ids: list[str],
    maximum_uses: int = 1000,
    expires_at: str = "2099-01-01T00:00:00+00:00",
    excluded_actions: list[str] | None = None,
    revoked_at: str | None = None,
) -> None:
    grants_dir = workspace.ai_team / "run-authorization-grants"
    grants_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "id": grant_id,
        "revision": 1,
        "issued_at": "2026-08-30T00:00:00+00:00",
        "issuing_authority": "cheikh MBACKE",
        "work_unit_ids": work_unit_ids,
        "allowed_commands": [],
        "allowed_environments": ["development", "test"],
        "maximum_spend": None,
        "maximum_duration_hours": 12,
        "expires_at": expires_at,
        "maximum_uses": maximum_uses,
        "uses_count": 0,
        "excluded_actions": excluded_actions
        or [
            "RecordGateDecision",
            "RecordAcceptance",
            "ResolveDecisionRequest",
            "ModifyConstitution",
            "ProductionAction",
        ],
        "revoked_at": revoked_at,
        "revoked_reason": "test revocation" if revoked_at else None,
    }
    (grants_dir / f"{grant_id}.json").write_text(json.dumps(document, indent=2), encoding="utf-8")


@pytest.fixture()
def run_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = REPO_ROOT / ".ai-team"
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    shutil.copy2(source / "project-profile.yaml", ai_team / "project-profile.yaml")
    shutil.copy2(source / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: execution\n", encoding="utf-8")
    (ai_team / "work-units").mkdir(parents=True)
    workspace = Workspace.from_root(tmp_path)
    _seed_grant(workspace, DEFAULT_GRANT_ID, work_unit_ids=["WU-A", "WU-NIGHT-001"])
    return workspace


def _seed_work_unit(
    workspace: Workspace, work_unit_id: str, *, status: str, scope_include: list[str] | None = None
) -> None:
    document = {
        "id": work_unit_id,
        "title": "Test work unit",
        "objective": {"result": "test"},
        "scope": {"include": scope_include or [], "exclude": []},
        "expected_behavior": "test behavior",
        "acceptance_criteria": ["ok"],
        "dependencies": [],
        "risk": {"class": "low", "reasons": []},
        "required_verification": {"unit_tests": True},
        "status": status,
        "revision": 1,
        "created_at": "2026-08-30T00:00:00+00:00",
        "updated_at": "2026-08-30T00:00:00+00:00",
        "events": [],
        "evidence": [],
        "outcomes": {
            "review_status": "pending",
            "audit_status": "not_required",
            "critical_open_items": [],
            "defects": [],
            "audit_findings": [],
            "human_acceptance": None,
        },
    }
    path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def _actor(role_id: str = "control-plane") -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-run-test",
        "role_id": role_id,
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _envelope(
    command_type: str,
    *,
    target: dict,
    payload: dict,
    key: str,
    role_id: str = "control-plane",
    **extra: dict,
) -> dict:
    envelope = {
        "protocol_version": "1.0",
        "command_id": f"CMD-{key}",
        "idempotency_key": f"idem-{key}",
        "correlation_id": "COR-run-test",
        "type": command_type,
        "issued_at": "2026-08-30T02:00:00Z",
        "actor": _actor(role_id),
        "target": target,
        "payload": payload,
    }
    envelope.update(extra)
    return envelope


def _passing_preflight() -> dict:
    return {
        "python": {"status": "pass", "detail": "ok"},
        "hooks_config": {"status": "pass", "detail": "ok"},
    }


def _open_run(
    run_id: str,
    *,
    work_unit_ids: list[str] | None = None,
    status: str = "pending",
    preflight: dict | None = None,
    grant_id: str | None = DEFAULT_GRANT_ID,
    execution_ceilings_by_work_unit: dict | None = None,
    maximum_parallel_workers: int | None = None,
) -> dict:
    payload = {
        "id": run_id,
        "opened_by": "operator",
        "work_unit_ids": work_unit_ids or ["WU-NIGHT-001"],
        "status": status,
        "preflight": preflight if preflight is not None else _passing_preflight(),
    }
    if execution_ceilings_by_work_unit is not None:
        payload["execution_ceilings_by_work_unit"] = execution_ceilings_by_work_unit
    if maximum_parallel_workers is not None:
        payload["maximum_parallel_workers"] = maximum_parallel_workers
    envelope = _envelope(
        "OpenRun",
        target={"kind": "run", "id": run_id},
        payload=payload,
        key=f"open-{run_id}",
    )
    if grant_id is not None:
        envelope["run_authorization"] = {"grant_id": grant_id}
    return envelope


def _tighten_ceiling(
    run_id: str,
    *,
    expected_revision: int,
    work_unit_id: str,
    dimension: str,
    new_state: str,
    reason: str = "risk escalation discovered mid-run",
) -> dict:
    return _envelope(
        "TightenExecutionCeiling",
        target={"kind": "run", "id": run_id, "expected_revision": expected_revision},
        payload={
            "work_unit_id": work_unit_id,
            "dimension": dimension,
            "new_state": new_state,
            "reason": reason,
        },
        key=f"tighten-{run_id}-{expected_revision}-{dimension}",
    )


def _record_integration_merge(
    merge_id: str,
    *,
    run_id: str,
    work_unit_id: str,
    lease_id: str,
    epoch: int,
    conflict_resolution_attempts: int = 0,
    revalidation_passed: bool = True,
    revalidation_evidence: list[str] | None = None,
) -> dict:
    return _envelope(
        "RecordIntegrationMerge",
        target={"kind": "integration_merge", "id": merge_id},
        payload={
            "run_id": run_id,
            "work_unit_id": work_unit_id,
            "worker_lease_id": lease_id,
            "epoch": epoch,
            "conflict_resolution_attempts": conflict_resolution_attempts,
            "revalidation_passed": revalidation_passed,
            "revalidation_evidence": revalidation_evidence or ["ci_run_ok"],
        },
        key=f"merge-{merge_id}",
    )


def _record_heartbeat(lease_id: str, *, run_id: str, epoch: int) -> dict:
    return _envelope(
        "RecordWorkerHeartbeat",
        target={"kind": "worker_lease", "id": lease_id},
        payload={"run_id": run_id, "epoch": epoch},
        key=f"heartbeat-{lease_id}-{epoch}",
    )


def _acquire_lease(lease_id: str, *, run_id: str, work_unit_id: str, worker_id: str) -> dict:
    return _envelope(
        "AcquireWorkerLease",
        target={"kind": "worker_lease", "id": lease_id},
        payload={
            "id": lease_id,
            "run_id": run_id,
            "work_unit_id": work_unit_id,
            "worker_id": worker_id,
        },
        key=f"lease-{lease_id}",
    )


def _record_attempt(
    attempt_id: str,
    *,
    run_id: str,
    work_unit_id: str,
    lease_id: str,
    epoch: int,
    status: str = "succeeded",
    step: str = "implement",
    summary: str | None = None,
) -> dict:
    payload = {
        "run_id": run_id,
        "work_unit_id": work_unit_id,
        "worker_lease_id": lease_id,
        "epoch": epoch,
        "step": step,
        "status": status,
    }
    if summary is not None:
        payload["summary"] = summary
    return _envelope(
        "RecordExecutionAttempt",
        target={"kind": "execution_attempt", "id": attempt_id},
        payload=payload,
        key=f"attempt-{attempt_id}",
    )


def _write_checkpoint(
    work_unit_id: str, *, run_id: str, lease_id: str, epoch: int, key_suffix: str
) -> dict:
    return _envelope(
        "WriteCheckpoint",
        target={"kind": "checkpoint", "id": work_unit_id},
        payload={
            "run_id": run_id,
            "worker_lease_id": lease_id,
            "epoch": epoch,
            "next_step": "continue implementation",
        },
        key=f"checkpoint-{work_unit_id}-{key_suffix}",
    )


def _close_run(
    run_id: str,
    *,
    expected_revision: int,
    status: str = "completed",
    stop_condition: str | None = None,
) -> dict:
    payload = {"status": status, "reason": "nightly window elapsed"}
    if stop_condition is not None:
        payload["stop_condition"] = stop_condition
    return _envelope(
        "CloseRun",
        target={"kind": "run", "id": run_id, "expected_revision": expected_revision},
        payload=payload,
        key=f"close-{run_id}-{expected_revision}-{stop_condition}",
    )


def _issue_grant(
    grant_id: str,
    *,
    work_unit_ids: list[str],
    expires_at: str = "2099-01-01T00:00:00+00:00",
    maximum_uses: int = 1,
    excluded_actions: list[str] | None = None,
    decision_menu: list[dict] | None = None,
    mission_artifact_ids: list[str] | None = None,
    auth_id: str | None = None,
) -> dict:
    payload = {
        "id": grant_id,
        "issuing_authority": "cheikh MBACKE",
        "work_unit_ids": work_unit_ids,
        "expires_at": expires_at,
        "maximum_uses": maximum_uses,
        "excluded_actions": excluded_actions
        or [
            "RecordGateDecision",
            "RecordAcceptance",
            "ResolveDecisionRequest",
            "ModifyConstitution",
            "ProductionAction",
        ],
    }
    if decision_menu is not None:
        payload["decision_menu"] = decision_menu
    if mission_artifact_ids is not None:
        payload["mission_artifact_ids"] = mission_artifact_ids
    return _envelope(
        "IssueRunAuthorizationGrant",
        target={"kind": "run_authorization_grant", "id": grant_id},
        payload=payload,
        key=f"issue-{grant_id}",
        human_authorization={"authorization_id": auth_id or f"AUTH-{grant_id}"},
    )


def _resolve_decision(
    decision_id: str,
    *,
    run_id: str,
    work_unit_id: str,
    trigger: dict,
    proposed_entry_id: str,
    evidence: list[str] | None = None,
) -> dict:
    return _envelope(
        "ResolveRunDecision",
        target={"kind": "run_decision", "id": decision_id},
        payload={
            "run_id": run_id,
            "work_unit_id": work_unit_id,
            "trigger": trigger,
            "proposed_entry_id": proposed_entry_id,
            "evidence": evidence or [],
        },
        key=f"decision-{decision_id}",
    )


def _revoke_grant(
    grant_id: str, *, expected_revision: int, reason: str = "operator kill switch", auth_id: str | None = None
) -> dict:
    return _envelope(
        "RevokeRunAuthorizationGrant",
        target={
            "kind": "run_authorization_grant",
            "id": grant_id,
            "expected_revision": expected_revision,
        },
        payload={"reason": reason},
        key=f"revoke-{grant_id}-{expected_revision}",
        human_authorization={"authorization_id": auth_id or f"AUTH-REVOKE-{grant_id}-{expected_revision}"},
    )


def _expire_lease_heartbeat(workspace: Workspace, lease_id: str) -> None:
    lease_path = workspace.ai_team / "runs" / "leases" / f"{lease_id}.yaml"
    document = yaml.safe_load(lease_path.read_text(encoding="utf-8"))
    stale = datetime.now(UTC) - timedelta(minutes=document["stalled_after_minutes"] + 1)
    document["heartbeat_at"] = stale.isoformat()
    lease_path.write_text(yaml.safe_dump(document), encoding="utf-8")


def test_open_run_via_gateway(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(_open_run("RUN-001"))
    assert exit_code == 0
    assert receipt["status"] == "accepted"
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-001.yaml").read_text(encoding="utf-8")
    )
    assert document["status"] == "pending"
    assert document["revision"] == 1
    assert document["leases_by_work_unit"] == {}


def test_open_run_rejects_manual_preflight_status(run_workspace: Workspace) -> None:
    """Document 6 §9.6 — a `manual` check must forbid opening an unattended Run."""
    gateway = CommandGateway(run_workspace)
    envelope = _open_run(
        "RUN-PREFLIGHT-MANUAL",
        preflight={
            "python": {"status": "pass", "detail": "ok"},
            "global_allowlist": {
                "status": "manual",
                "detail": "confirm Approval mode=Allowlist in /config",
            },
        },
    )
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert not (run_workspace.ai_team / "runs" / "RUN-PREFLIGHT-MANUAL.yaml").exists()


def test_open_run_rejects_blocked_preflight_status(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    envelope = _open_run(
        "RUN-PREFLIGHT-BLOCKED",
        preflight={"allowlist_smoke": {"status": "blocked", "detail": "hooks not wired"}},
    )
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_open_run_rejects_missing_preflight(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    envelope = _open_run("RUN-NO-PREFLIGHT", preflight={})
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_SCHEMA.value


def test_open_run_rejects_duplicate(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-DUP"))
    duplicate = _open_run("RUN-DUP")
    duplicate["command_id"] = "CMD-open-RUN-DUP-retry"
    duplicate["idempotency_key"] = "idem-open-RUN-DUP-retry"
    receipt, exit_code = gateway.execute_command(duplicate)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.ALREADY_EXISTS.value


def test_acquire_worker_lease_starts_at_epoch_one(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-002", work_unit_ids=["WU-A"]))
    receipt, exit_code = gateway.execute_command(
        _acquire_lease("LEASE-001", run_id="RUN-002", work_unit_id="WU-A", worker_id="worker-1")
    )
    assert exit_code == 0
    lease = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "leases" / "LEASE-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert lease["epoch"] == 1
    assert lease["status"] == "active"
    run_document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-002.yaml").read_text(encoding="utf-8")
    )
    assert run_document["leases_by_work_unit"]["WU-A"] == {"lease_id": "LEASE-001", "epoch": 1}


def test_acquire_worker_lease_conflicts_while_fresh(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-003", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-A1", run_id="RUN-003", work_unit_id="WU-A", worker_id="worker-1")
    )
    receipt, exit_code = gateway.execute_command(
        _acquire_lease("LEASE-A2", run_id="RUN-003", work_unit_id="WU-A", worker_id="worker-2")
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_acquire_worker_lease_rejects_beyond_maximum_parallel_workers(
    run_workspace: Workspace,
) -> None:
    """Document 6 §11 — the cap is mechanical, independent of how many threads exist."""
    _seed_grant(run_workspace, "GRANT-PARALLEL", work_unit_ids=["WU-A", "WU-B"])
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _open_run(
            "RUN-PARALLEL-001",
            work_unit_ids=["WU-A", "WU-B"],
            grant_id="GRANT-PARALLEL",
            maximum_parallel_workers=1,
        )
    )
    gateway.execute_command(
        _acquire_lease("LEASE-P1", run_id="RUN-PARALLEL-001", work_unit_id="WU-A", worker_id="w1")
    )

    receipt, exit_code = gateway.execute_command(
        _acquire_lease("LEASE-P2", run_id="RUN-PARALLEL-001", work_unit_id="WU-B", worker_id="w2")
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_acquire_worker_lease_reassignment_ignores_parallel_cap(
    run_workspace: Workspace,
) -> None:
    """Reassigning a dead worker's lease replaces it — it must not be blocked by the cap
    it does not grow."""
    _seed_grant(run_workspace, "GRANT-PARALLEL-2", work_unit_ids=["WU-A"])
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _open_run(
            "RUN-PARALLEL-002",
            work_unit_ids=["WU-A"],
            grant_id="GRANT-PARALLEL-2",
            maximum_parallel_workers=1,
        )
    )
    gateway.execute_command(
        _acquire_lease("LEASE-P3", run_id="RUN-PARALLEL-002", work_unit_id="WU-A", worker_id="w1")
    )
    _expire_lease_heartbeat(run_workspace, "LEASE-P3")

    receipt, exit_code = gateway.execute_command(
        _acquire_lease("LEASE-P4", run_id="RUN-PARALLEL-002", work_unit_id="WU-A", worker_id="w2")
    )
    assert exit_code == 0


def test_record_execution_attempt_with_current_epoch_succeeds(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-004", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-B1", run_id="RUN-004", work_unit_id="WU-A", worker_id="worker-1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-001", run_id="RUN-004", work_unit_id="WU-A", lease_id="LEASE-B1", epoch=1
        )
    )
    assert exit_code == 0
    assert receipt["status"] == "accepted"


def test_fencing_rejects_write_from_superseded_lease_epoch(run_workspace: Workspace) -> None:
    """Document 6 §15 — a reassigned worker's late write must be rejected, not silently applied."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-005", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-C1", run_id="RUN-005", work_unit_id="WU-A", worker_id="worker-1")
    )

    # Simulate worker-1 going silent long enough to be considered stalled.
    _expire_lease_heartbeat(run_workspace, "LEASE-C1")

    reassign_receipt, reassign_exit = gateway.execute_command(
        _acquire_lease("LEASE-C2", run_id="RUN-005", work_unit_id="WU-A", worker_id="worker-2")
    )
    assert reassign_exit == 0
    new_lease = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "leases" / "LEASE-C2.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert new_lease["epoch"] == 2
    old_lease = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "leases" / "LEASE-C1.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert old_lease["status"] == "superseded"
    assert old_lease["superseded_by"] == "LEASE-C2"

    # worker-1 reappears and tries to write against its old (now stale) epoch.
    stale_receipt, stale_exit = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-STALE", run_id="RUN-005", work_unit_id="WU-A", lease_id="LEASE-C1", epoch=1
        )
    )
    assert stale_exit == 5
    assert stale_receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value

    # worker-2 (the reassigned, current epoch) can write successfully.
    current_receipt, current_exit = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CURRENT", run_id="RUN-005", work_unit_id="WU-A", lease_id="LEASE-C2", epoch=2
        )
    )
    assert current_exit == 0
    assert current_receipt["status"] == "accepted"


def test_write_checkpoint_fencing_rejects_stale_epoch(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-006", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-D1", run_id="RUN-006", work_unit_id="WU-A", worker_id="worker-1")
    )
    _expire_lease_heartbeat(run_workspace, "LEASE-D1")
    gateway.execute_command(
        _acquire_lease("LEASE-D2", run_id="RUN-006", work_unit_id="WU-A", worker_id="worker-2")
    )

    stale_receipt, stale_exit = gateway.execute_command(
        _write_checkpoint("WU-A", run_id="RUN-006", lease_id="LEASE-D1", epoch=1, key_suffix="stale")
    )
    assert stale_exit == 5
    assert stale_receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value

    current_receipt, current_exit = gateway.execute_command(
        _write_checkpoint(
            "WU-A", run_id="RUN-006", lease_id="LEASE-D2", epoch=2, key_suffix="current"
        )
    )
    assert current_exit == 0
    checkpoint = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "checkpoints" / "WU-A.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["epoch"] == 2


def test_close_run_happy_path(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-007", status="active"))
    receipt, exit_code = gateway.execute_command(_close_run("RUN-007", expected_revision=1))
    assert exit_code == 0
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-007.yaml").read_text(encoding="utf-8")
    )
    assert document["status"] == "completed"
    assert document["revision"] == 2
    assert document["closed_at"] is not None


def test_close_run_rejects_stale_revision(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-008"))
    receipt, exit_code = gateway.execute_command(_close_run("RUN-008", expected_revision=99))
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_close_run_stopped_requires_a_stop_condition(run_workspace: Workspace) -> None:
    """Document 6 §9.5/§11 — free-text reasons cannot substitute for a recognized condition."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-009", status="active"))
    receipt, exit_code = gateway.execute_command(
        _close_run("RUN-009", expected_revision=1, status="stopped")
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_SCHEMA.value


def test_close_run_stopped_rejects_unrecognized_stop_condition(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-010", status="active"))
    receipt, exit_code = gateway.execute_command(
        _close_run(
            "RUN-010",
            expected_revision=1,
            status="stopped",
            stop_condition="the-agent-felt-like-it",
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_SCHEMA.value


def test_close_run_stopped_with_recognized_condition_emits_immediate_alert(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-011", status="active"))
    receipt, exit_code = gateway.execute_command(
        _close_run(
            "RUN-011", expected_revision=1, status="stopped", stop_condition="fencing_conflict"
        )
    )
    assert exit_code == 0
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-011.yaml").read_text(encoding="utf-8")
    )
    assert document["status"] == "stopped"
    assert document["stop_condition"] == "fencing_conflict"

    assert len(receipt["domain_events"]) == 1
    event_id = receipt["domain_events"][0]
    event_path = run_workspace.ai_team / "events" / f"{event_id}.yaml"
    assert event_path.is_file()
    event = yaml.safe_load(event_path.read_text(encoding="utf-8"))
    assert event["type"] == "BLOCKER"
    assert event["requires_human"] is True
    assert event["details"]["stop_condition"] == "fencing_conflict"


def test_convergence_loop_stops_after_maximum_attempts_per_step(run_workspace: Workspace) -> None:
    """Document 6 §9.3 — the (default) 3rd attempt at a step is the last one allowed."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CONV-001", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CONV-1", run_id="RUN-CONV-001", work_unit_id="WU-A", worker_id="w1")
    )

    for n in range(1, 4):
        receipt, exit_code = gateway.execute_command(
            _record_attempt(
                f"ATTEMPT-CONV-{n}",
                run_id="RUN-CONV-001",
                work_unit_id="WU-A",
                lease_id="LEASE-CONV-1",
                epoch=1,
                status="failed",
                summary=f"distinct failure #{n}",
            )
        )
        assert exit_code == 0, receipt

    # The 3rd attempt (== default maximum_attempts_per_step) must have raised the alert.
    assert receipt["details"]["convergence_exhausted"] is True
    assert receipt["details"]["convergence_exhaustion_reason"] == "step_attempts_exhausted"
    assert len(receipt["domain_events"]) == 1
    event = yaml.safe_load(
        (run_workspace.ai_team / "events" / f"{receipt['domain_events'][0]}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert event["requires_human"] is True

    # A 4th attempt at the same step is refused outright — the alert already exists.
    blocked_receipt, blocked_exit = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CONV-4",
            run_id="RUN-CONV-001",
            work_unit_id="WU-A",
            lease_id="LEASE-CONV-1",
            epoch=1,
            status="failed",
            summary="distinct failure #4",
        )
    )
    assert blocked_exit == 3
    assert blocked_receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_convergence_loop_stops_on_identical_repeated_failure(run_workspace: Workspace) -> None:
    """Two consecutive identical failures stop the loop before the numeric cap is reached."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CONV-002", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CONV-2", run_id="RUN-CONV-002", work_unit_id="WU-A", worker_id="w1")
    )

    for n in range(1, 3):
        receipt, exit_code = gateway.execute_command(
            _record_attempt(
                f"ATTEMPT-REPEAT-{n}",
                run_id="RUN-CONV-002",
                work_unit_id="WU-A",
                lease_id="LEASE-CONV-2",
                epoch=1,
                status="failed",
                summary="TypeError: same root cause every time",
            )
        )
        assert exit_code == 0

    assert receipt["details"]["convergence_exhausted"] is True
    assert receipt["details"]["convergence_exhaustion_reason"] == "identical_failure_repeated"

    blocked_receipt, blocked_exit = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-REPEAT-3",
            run_id="RUN-CONV-002",
            work_unit_id="WU-A",
            lease_id="LEASE-CONV-2",
            epoch=1,
            status="failed",
            summary="TypeError: same root cause every time",
        )
    )
    assert blocked_exit == 3
    assert blocked_receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_convergence_loop_remediation_cycle_cap_is_stricter(run_workspace: Workspace) -> None:
    """Document 6 §9.3 — maximum_remediation_cycles (default 2) applies to the remediation step."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CONV-003", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CONV-3", run_id="RUN-CONV-003", work_unit_id="WU-A", worker_id="w1")
    )

    for n in range(1, 3):
        receipt, exit_code = gateway.execute_command(
            _record_attempt(
                f"ATTEMPT-REMEDIATE-{n}",
                run_id="RUN-CONV-003",
                work_unit_id="WU-A",
                lease_id="LEASE-CONV-3",
                epoch=1,
                status="failed",
                step="remediation",
                summary=f"remediation attempt #{n} failed differently",
            )
        )
        assert exit_code == 0

    assert receipt["details"]["convergence_exhausted"] is True
    assert receipt["details"]["convergence_exhaustion_reason"] == "remediation_cycles_exhausted"


def test_issue_run_authorization_grant_via_gateway(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _issue_grant("GRANT-001", work_unit_ids=["WU-A"])
    )
    assert exit_code == 0
    document = json.loads(
        (run_workspace.ai_team / "run-authorization-grants" / "GRANT-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["uses_count"] == 0
    assert document["revoked_at"] is None


def test_issue_run_authorization_grant_requires_minimum_excluded_actions(
    run_workspace: Workspace,
) -> None:
    """Document 6 §8 — a grant can never be issued without the baseline exclusions."""
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _issue_grant("GRANT-WEAK", work_unit_ids=["WU-A"], excluded_actions=["RecordGateDecision"])
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert not (run_workspace.ai_team / "run-authorization-grants" / "GRANT-WEAK.json").exists()


def test_open_run_rejects_missing_grant_reference(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(_open_run("RUN-NO-GRANT", grant_id=None))
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.HUMAN_AUTH_REQUIRED.value


def test_open_run_rejects_unknown_grant(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    envelope = _open_run("RUN-UNKNOWN-GRANT")
    envelope["run_authorization"] = {"grant_id": "GRANT-DOES-NOT-EXIST"}
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.NOT_FOUND.value


def test_open_run_rejects_work_units_not_covered_by_grant(run_workspace: Workspace) -> None:
    _seed_grant(run_workspace, "GRANT-NARROW", work_unit_ids=["WU-COVERED"])
    gateway = CommandGateway(run_workspace)
    envelope = _open_run(
        "RUN-UNCOVERED", work_unit_ids=["WU-OTHER"], grant_id="GRANT-NARROW"
    )
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_open_run_rejects_exhausted_grant(run_workspace: Workspace) -> None:
    _seed_grant(run_workspace, "GRANT-SINGLE-USE", work_unit_ids=["WU-A"], maximum_uses=1)
    gateway = CommandGateway(run_workspace)
    first_receipt, first_exit = gateway.execute_command(
        _open_run("RUN-FIRST", work_unit_ids=["WU-A"], grant_id="GRANT-SINGLE-USE")
    )
    assert first_exit == 0

    second_receipt, second_exit = gateway.execute_command(
        _open_run("RUN-SECOND", work_unit_ids=["WU-A"], grant_id="GRANT-SINGLE-USE")
    )
    assert second_exit == 4
    assert second_receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_open_run_rejects_expired_grant(run_workspace: Workspace) -> None:
    _seed_grant(
        run_workspace,
        "GRANT-EXPIRED",
        work_unit_ids=["WU-A"],
        expires_at="2020-01-01T00:00:00+00:00",
    )
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _open_run("RUN-EXPIRED-GRANT", work_unit_ids=["WU-A"], grant_id="GRANT-EXPIRED")
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_revoke_run_authorization_grant_via_gateway(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_issue_grant("GRANT-002", work_unit_ids=["WU-A"]))
    receipt, exit_code = gateway.execute_command(_revoke_grant("GRANT-002", expected_revision=1))
    assert exit_code == 0
    document = json.loads(
        (run_workspace.ai_team / "run-authorization-grants" / "GRANT-002.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["revoked_at"] is not None
    assert document["revoked_reason"] == "operator kill switch"


def test_revoke_run_authorization_grant_rejects_double_revoke(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_issue_grant("GRANT-003", work_unit_ids=["WU-A"]))
    gateway.execute_command(_revoke_grant("GRANT-003", expected_revision=1))
    receipt, exit_code = gateway.execute_command(
        _revoke_grant("GRANT-003", expected_revision=2, auth_id="AUTH-REVOKE-GRANT-003-second")
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_revoked_grant_blocks_further_run_scoped_commands(run_workspace: Workspace) -> None:
    """Document 6 §8/§9.7 — revocation is the kill switch: it must stop an already-open Run."""
    _seed_grant(run_workspace, "GRANT-KILLSWITCH", work_unit_ids=["WU-A"], maximum_uses=5)
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _open_run("RUN-KILLSWITCH", work_unit_ids=["WU-A"], grant_id="GRANT-KILLSWITCH")
    )

    # Revoke the grant directly (bypassing IssueRunAuthorizationGrant, which was
    # never used to create this seeded grant) by writing revoked_at, mirroring
    # what RevokeRunAuthorizationGrant would persist.
    grant_path = run_workspace.ai_team / "run-authorization-grants" / "GRANT-KILLSWITCH.json"
    document = json.loads(grant_path.read_text(encoding="utf-8"))
    document["revoked_at"] = "2026-08-30T03:00:00+00:00"
    document["revoked_reason"] = "kill switch triggered"
    document["revision"] += 1
    grant_path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    receipt, exit_code = gateway.execute_command(
        _acquire_lease(
            "LEASE-KILLSWITCH", run_id="RUN-KILLSWITCH", work_unit_id="WU-A", worker_id="w1"
        )
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def _dependency_menu_entry(**overrides) -> dict:
    entry = {
        "id": "DM-DEPENDENCY-001",
        "trigger": {
            "type": "dependency_choice",
            "conditions": {"production_runtime": False},
        },
        "authorized_option": {"option_id": "use_existing_dependency"},
        "scope": {"work_units": ["WU-A"]},
        "maximum_uses": 1,
        "expires_at": "2099-01-01T00:00:00+00:00",
        "required_evidence": ["compatibility_test"],
    }
    entry.update(overrides)
    return entry


def test_issue_grant_with_decision_menu_entry(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-001", work_unit_ids=["WU-A"], decision_menu=[_dependency_menu_entry()]
        )
    )
    assert exit_code == 0
    document = json.loads(
        (run_workspace.ai_team / "run-authorization-grants" / "GRANT-MENU-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["decision_menu"][0]["uses_count"] == 0


def test_issue_grant_rejects_duplicate_decision_menu_entry_ids(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-DUP",
            work_unit_ids=["WU-A"],
            decision_menu=[_dependency_menu_entry(), _dependency_menu_entry()],
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_resolve_run_decision_matched_and_valid(run_workspace: Workspace) -> None:
    """Document 6 §5.4 — a validated correspondence resolves automatically and is traced."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-002", work_unit_ids=["WU-A"], decision_menu=[_dependency_menu_entry()]
        )
    )
    gateway.execute_command(
        _open_run("RUN-MENU-001", work_unit_ids=["WU-A"], grant_id="GRANT-MENU-002")
    )

    receipt, exit_code = gateway.execute_command(
        _resolve_decision(
            "DECISION-001",
            run_id="RUN-MENU-001",
            work_unit_id="WU-A",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=["compatibility_test"],
        )
    )
    assert exit_code == 0
    assert receipt["details"]["resolved"] is True
    assert receipt["details"]["rejection_reason"] is None

    grant_document = json.loads(
        (run_workspace.ai_team / "run-authorization-grants" / "GRANT-MENU-002.json").read_text(
            encoding="utf-8"
        )
    )
    assert grant_document["decision_menu"][0]["uses_count"] == 1

    decision = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "decisions" / "DECISION-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert decision["resolved"] is True


def test_resolve_run_decision_trigger_mismatch_is_not_resolved(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-003", work_unit_ids=["WU-A"], decision_menu=[_dependency_menu_entry()]
        )
    )
    gateway.execute_command(
        _open_run("RUN-MENU-002", work_unit_ids=["WU-A"], grant_id="GRANT-MENU-003")
    )

    receipt, exit_code = gateway.execute_command(
        _resolve_decision(
            "DECISION-002",
            run_id="RUN-MENU-002",
            work_unit_id="WU-A",
            trigger={"type": "dependency_choice", "production_runtime": True},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=["compatibility_test"],
        )
    )
    assert exit_code == 0
    assert receipt["details"]["resolved"] is False
    assert receipt["details"]["rejection_reason"] == "trigger_mismatch"


def test_resolve_run_decision_missing_evidence_is_not_resolved(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-004", work_unit_ids=["WU-A"], decision_menu=[_dependency_menu_entry()]
        )
    )
    gateway.execute_command(
        _open_run("RUN-MENU-003", work_unit_ids=["WU-A"], grant_id="GRANT-MENU-004")
    )

    receipt, exit_code = gateway.execute_command(
        _resolve_decision(
            "DECISION-003",
            run_id="RUN-MENU-003",
            work_unit_id="WU-A",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=[],
        )
    )
    assert exit_code == 0
    assert receipt["details"]["resolved"] is False
    assert receipt["details"]["rejection_reason"] == "missing_required_evidence"


def test_resolve_run_decision_out_of_scope_work_unit_is_not_resolved(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-005",
            work_unit_ids=["WU-A", "WU-B"],
            decision_menu=[_dependency_menu_entry()],
        )
    )
    gateway.execute_command(
        _open_run("RUN-MENU-004", work_unit_ids=["WU-A", "WU-B"], grant_id="GRANT-MENU-005")
    )

    receipt, exit_code = gateway.execute_command(
        _resolve_decision(
            "DECISION-004",
            run_id="RUN-MENU-004",
            work_unit_id="WU-B",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=["compatibility_test"],
        )
    )
    assert exit_code == 0
    assert receipt["details"]["resolved"] is False
    assert receipt["details"]["rejection_reason"] == "out_of_scope_work_unit"


def test_resolve_run_decision_maximum_uses_reached_is_not_resolved(
    run_workspace: Workspace,
) -> None:
    """Document 6 §5.4 — a spent entry never resolves twice, whatever the trigger looks like."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant(
            "GRANT-MENU-006", work_unit_ids=["WU-A"], decision_menu=[_dependency_menu_entry()]
        )
    )
    gateway.execute_command(
        _open_run("RUN-MENU-005", work_unit_ids=["WU-A"], grant_id="GRANT-MENU-006")
    )

    first, first_exit = gateway.execute_command(
        _resolve_decision(
            "DECISION-005",
            run_id="RUN-MENU-005",
            work_unit_id="WU-A",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=["compatibility_test"],
        )
    )
    assert first["details"]["resolved"] is True

    second, second_exit = gateway.execute_command(
        _resolve_decision(
            "DECISION-006",
            run_id="RUN-MENU-005",
            work_unit_id="WU-A",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=["compatibility_test"],
        )
    )
    assert second_exit == 0
    assert second["details"]["resolved"] is False
    assert second["details"]["rejection_reason"] == "maximum_uses_reached"


def test_resolve_run_decision_unknown_entry(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant("GRANT-MENU-007", work_unit_ids=["WU-A"], decision_menu=[])
    )
    gateway.execute_command(
        _open_run("RUN-MENU-006", work_unit_ids=["WU-A"], grant_id="GRANT-MENU-007")
    )

    receipt, exit_code = gateway.execute_command(
        _resolve_decision(
            "DECISION-007",
            run_id="RUN-MENU-006",
            work_unit_id="WU-A",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DOES-NOT-EXIST",
            evidence=[],
        )
    )
    assert exit_code == 0
    assert receipt["details"]["resolved"] is False
    assert receipt["details"]["rejection_reason"] == "entry_not_found"


def test_open_run_defaults_execution_ceiling_for_unspecified_work_unit(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(_open_run("RUN-CEIL-001", work_unit_ids=["WU-A"]))
    assert exit_code == 0
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-CEIL-001.yaml").read_text(encoding="utf-8")
    )
    ceiling = document["execution_ceilings_by_work_unit"]["WU-A"]
    assert ceiling["sandbox_implementation"] == "allowed"
    assert ceiling["integration_branch_merge"] == "conditional"
    assert ceiling["protected_branch_merge"] == "forbidden"
    assert ceiling["production_action"] == "forbidden"


def test_open_run_rejects_execution_ceiling_permitting_protected_branch_merge(
    run_workspace: Workspace,
) -> None:
    """Document 6 §2.4/§7.1/§9.8 — no exception, for any preset."""
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _open_run(
            "RUN-CEIL-002",
            work_unit_ids=["WU-A"],
            execution_ceilings_by_work_unit={"WU-A": {"protected_branch_merge": "allowed"}},
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert not (run_workspace.ai_team / "runs" / "RUN-CEIL-002.yaml").exists()


def test_open_run_rejects_execution_ceiling_permitting_production_action(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _open_run(
            "RUN-CEIL-003",
            work_unit_ids=["WU-A"],
            execution_ceilings_by_work_unit={"WU-A": {"production_action": "conditional"}},
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_record_execution_attempt_rejects_step_beyond_forbidden_ceiling(
    run_workspace: Workspace,
) -> None:
    """Document 6 §15 — rejected by the Core, not merely discouraged."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-004", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CEIL-1", run_id="RUN-CEIL-004", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CEIL-1",
            run_id="RUN-CEIL-004",
            work_unit_id="WU-A",
            lease_id="LEASE-CEIL-1",
            epoch=1,
            step="protected_branch_merge",
        )
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_record_execution_attempt_rejects_conditional_step_without_approval(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-005", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CEIL-2", run_id="RUN-CEIL-005", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CEIL-2",
            run_id="RUN-CEIL-005",
            work_unit_id="WU-A",
            lease_id="LEASE-CEIL-2",
            epoch=1,
            step="integration_branch_merge",
        )
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_record_execution_attempt_allows_step_within_ceiling(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-006", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CEIL-3", run_id="RUN-CEIL-006", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CEIL-3",
            run_id="RUN-CEIL-006",
            work_unit_id="WU-A",
            lease_id="LEASE-CEIL-3",
            epoch=1,
            step="sandbox_implementation",
        )
    )
    assert exit_code == 0


def test_record_execution_attempt_gates_integration_review_by_ceiling_default(
    run_workspace: Workspace,
) -> None:
    """The orchestrator's real dispatch step is "integration_review", not the
    ceiling dimension name "integration_branch_merge" — it must resolve to the
    same dimension and be rejected under the default "conditional" state, same
    as a direct request for the dimension itself already is."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-008", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-CEIL-4", run_id="RUN-CEIL-008", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CEIL-4",
            run_id="RUN-CEIL-008",
            work_unit_id="WU-A",
            lease_id="LEASE-CEIL-4",
            epoch=1,
            step="integration_review",
        )
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_record_execution_attempt_rejects_integration_review_when_ceiling_forbidden(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _open_run(
            "RUN-CEIL-009",
            work_unit_ids=["WU-A"],
            execution_ceilings_by_work_unit={
                "WU-A": {"integration_branch_merge": "forbidden"}
            },
        )
    )
    gateway.execute_command(
        _acquire_lease("LEASE-CEIL-5", run_id="RUN-CEIL-009", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CEIL-5",
            run_id="RUN-CEIL-009",
            work_unit_id="WU-A",
            lease_id="LEASE-CEIL-5",
            epoch=1,
            step="integration_review",
        )
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_record_execution_attempt_allows_integration_review_when_ceiling_allowed(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _open_run(
            "RUN-CEIL-010",
            work_unit_ids=["WU-A"],
            execution_ceilings_by_work_unit={
                "WU-A": {"integration_branch_merge": "allowed"}
            },
        )
    )
    gateway.execute_command(
        _acquire_lease("LEASE-CEIL-6", run_id="RUN-CEIL-010", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_attempt(
            "ATTEMPT-CEIL-6",
            run_id="RUN-CEIL-010",
            work_unit_id="WU-A",
            lease_id="LEASE-CEIL-6",
            epoch=1,
            step="integration_review",
        )
    )
    assert exit_code == 0


def test_tighten_execution_ceiling_escalates_successfully(run_workspace: Workspace) -> None:
    """Document 6 §7.3 — escalation is automatic and requires no human authorization."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-007", work_unit_ids=["WU-A"]))
    receipt, exit_code = gateway.execute_command(
        _tighten_ceiling(
            "RUN-CEIL-007",
            expected_revision=1,
            work_unit_id="WU-A",
            dimension="integration_branch_merge",
            new_state="forbidden",
        )
    )
    assert exit_code == 0
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-CEIL-007.yaml").read_text(encoding="utf-8")
    )
    assert document["execution_ceilings_by_work_unit"]["WU-A"]["integration_branch_merge"] == (
        "forbidden"
    )
    assert document["revision"] == 2


def test_tighten_execution_ceiling_rejects_loosening(run_workspace: Workspace) -> None:
    """Document 6 §7.3 — de-escalation without human validation has no code path at all."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-008", work_unit_ids=["WU-A"]))
    receipt, exit_code = gateway.execute_command(
        _tighten_ceiling(
            "RUN-CEIL-008",
            expected_revision=1,
            work_unit_id="WU-A",
            dimension="protected_branch_merge",
            new_state="conditional",
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_tighten_execution_ceiling_rejects_holding_same_state(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-CEIL-009", work_unit_ids=["WU-A"]))
    receipt, exit_code = gateway.execute_command(
        _tighten_ceiling(
            "RUN-CEIL-009",
            expected_revision=1,
            work_unit_id="WU-A",
            dimension="integration_branch_merge",
            new_state="conditional",
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_open_run_sets_default_integration_branch(run_workspace: Workspace) -> None:
    """Document 6 §9.8 — dedicated to the Run, distinct from individual Work Unit branches."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-GIT-001", work_unit_ids=["WU-A"]))
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "RUN-GIT-001.yaml").read_text(encoding="utf-8")
    )
    assert document["integration_branch"] == "integration/RUN-GIT-001"


def test_record_integration_merge_succeeds_within_bounds(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-GIT-002", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-GIT-1", run_id="RUN-GIT-002", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_integration_merge(
            "MERGE-001",
            run_id="RUN-GIT-002",
            work_unit_id="WU-A",
            lease_id="LEASE-GIT-1",
            epoch=1,
            conflict_resolution_attempts=1,
        )
    )
    assert exit_code == 0
    document = yaml.safe_load(
        (run_workspace.ai_team / "runs" / "integration-merges" / "MERGE-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert document["integration_branch"] == "integration/RUN-GIT-002"
    assert document["revalidation_passed"] is True


def test_record_integration_merge_rejects_when_ceiling_forbidden(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-GIT-003", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-GIT-2", run_id="RUN-GIT-003", work_unit_id="WU-A", worker_id="w1")
    )
    gateway.execute_command(
        _tighten_ceiling(
            "RUN-GIT-003",
            expected_revision=1,
            work_unit_id="WU-A",
            dimension="integration_branch_merge",
            new_state="forbidden",
        )
    )
    receipt, exit_code = gateway.execute_command(
        _record_integration_merge(
            "MERGE-002",
            run_id="RUN-GIT-003",
            work_unit_id="WU-A",
            lease_id="LEASE-GIT-2",
            epoch=1,
        )
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_record_integration_merge_rejects_exhausted_conflict_resolution(
    run_workspace: Workspace,
) -> None:
    """Document 6 §9.8 — "mêmes limites de tentative que §9.3": never an unbounded retry loop."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-GIT-004", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-GIT-3", run_id="RUN-GIT-004", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_integration_merge(
            "MERGE-003",
            run_id="RUN-GIT-004",
            work_unit_id="WU-A",
            lease_id="LEASE-GIT-3",
            epoch=1,
            conflict_resolution_attempts=3,  # == default maximum_attempts_per_step
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_record_integration_merge_rejects_without_revalidation(run_workspace: Workspace) -> None:
    """Document 6 §9.8 — "revalidation complète après chaque fusion": never optional."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-GIT-005", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-GIT-4", run_id="RUN-GIT-005", work_unit_id="WU-A", worker_id="w1")
    )
    receipt, exit_code = gateway.execute_command(
        _record_integration_merge(
            "MERGE-004",
            run_id="RUN-GIT-005",
            work_unit_id="WU-A",
            lease_id="LEASE-GIT-4",
            epoch=1,
            revalidation_passed=False,
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_record_integration_merge_rejects_stale_epoch(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-GIT-006", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-GIT-5", run_id="RUN-GIT-006", work_unit_id="WU-A", worker_id="w1")
    )
    _expire_lease_heartbeat(run_workspace, "LEASE-GIT-5")
    gateway.execute_command(
        _acquire_lease("LEASE-GIT-6", run_id="RUN-GIT-006", work_unit_id="WU-A", worker_id="w2")
    )
    receipt, exit_code = gateway.execute_command(
        _record_integration_merge(
            "MERGE-005",
            run_id="RUN-GIT-006",
            work_unit_id="WU-A",
            lease_id="LEASE-GIT-5",
            epoch=1,
        )
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_run_morning_report_requires_run_id(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    with pytest.raises(GatewayError) as exc_info:
        gateway.query("run-morning-report", args={})
    assert exc_info.value.code == ErrorCode.INVALID_SCHEMA


def test_run_morning_report_unknown_run(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    with pytest.raises(GatewayError) as exc_info:
        gateway.query("run-morning-report", args={"run_id": "RUN-DOES-NOT-EXIST"})
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_run_morning_report_aggregates_full_session(run_workspace: Workspace) -> None:
    """Document 6 §13 — one grouped report, covering every bullet in the spec."""
    gateway = CommandGateway(run_workspace)
    work_unit_ids = ["WU-DONE", "WU-PAUSED", "WU-CANCELLED", "WU-ESC"]
    gateway.execute_command(
        _issue_grant(
            "GRANT-REPORT",
            work_unit_ids=work_unit_ids,
            maximum_uses=1,
            decision_menu=[_dependency_menu_entry(scope={"work_units": ["WU-DONE"]})],
        )
    )
    gateway.execute_command(
        _open_run("RUN-REPORT-001", work_unit_ids=work_unit_ids, grant_id="GRANT-REPORT")
    )

    # WU-DONE: successful attempt, a resolved automatic decision, later reassigned.
    gateway.execute_command(
        _acquire_lease(
            "LEASE-REPORT-DONE", run_id="RUN-REPORT-001", work_unit_id="WU-DONE", worker_id="w1"
        )
    )
    gateway.execute_command(
        _record_attempt(
            "ATTEMPT-REPORT-DONE",
            run_id="RUN-REPORT-001",
            work_unit_id="WU-DONE",
            lease_id="LEASE-REPORT-DONE",
            epoch=1,
            status="succeeded",
        )
    )
    gateway.execute_command(
        _resolve_decision(
            "DECISION-REPORT-001",
            run_id="RUN-REPORT-001",
            work_unit_id="WU-DONE",
            trigger={"type": "dependency_choice", "production_runtime": False},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=["compatibility_test"],
        )
    )
    _seed_work_unit(run_workspace, "WU-DONE", status="done")

    # WU-PAUSED: an unresolved decision leaves it waiting on a human.
    gateway.execute_command(
        _resolve_decision(
            "DECISION-REPORT-002",
            run_id="RUN-REPORT-001",
            work_unit_id="WU-PAUSED",
            trigger={"type": "unmapped_fork"},
            proposed_entry_id="DM-DEPENDENCY-001",
            evidence=[],
        )
    )
    _seed_work_unit(run_workspace, "WU-PAUSED", status="waiting_decision")

    # WU-CANCELLED: no Run-side activity, just its own terminal status.
    _seed_work_unit(run_workspace, "WU-CANCELLED", status="cancelled")

    # WU-ESC: a risk escalation with its justification.
    gateway.execute_command(
        _tighten_ceiling(
            "RUN-REPORT-001",
            expected_revision=1,
            work_unit_id="WU-ESC",
            dimension="integration_branch_merge",
            new_state="forbidden",
        )
    )

    # A stalled worker on WU-DONE gets reassigned — an anomaly worth surfacing.
    _expire_lease_heartbeat(run_workspace, "LEASE-REPORT-DONE")
    gateway.execute_command(
        _acquire_lease(
            "LEASE-REPORT-DONE-2",
            run_id="RUN-REPORT-001",
            work_unit_id="WU-DONE",
            worker_id="w2",
        )
    )

    # Close with a recognized stop condition — its BLOCKER event must surface too.
    gateway.execute_command(
        _close_run(
            "RUN-REPORT-001",
            expected_revision=2,
            status="stopped",
            stop_condition="repeated_systemic_failure",
        )
    )

    result = gateway.query("run-morning-report", args={"run_id": "RUN-REPORT-001"})
    report = result["data"]

    assert report["status"] == "stopped"
    assert report["stop_condition"] == "repeated_systemic_failure"

    assert {wu["work_unit_id"] for wu in report["completed_work_units"]} == {"WU-DONE"}
    assert report["completed_work_units"][0]["successful_attempts"] == ["ATTEMPT-REPORT-DONE"]

    assert {wu["work_unit_id"] for wu in report["paused_work_units"]} == {"WU-PAUSED"}
    pending = report["paused_work_units"][0]["pending_decisions"]
    assert pending[0]["decision_id"] == "DECISION-REPORT-002"
    assert pending[0]["rejection_reason"] is not None

    assert {wu["work_unit_id"] for wu in report["cancelled_work_units"]} == {"WU-CANCELLED"}

    assert len(report["automatic_decision_resolutions"]) == 1
    assert report["automatic_decision_resolutions"][0]["decision_id"] == "DECISION-REPORT-001"

    assert len(report["risk_escalations"]) == 1
    assert report["risk_escalations"][0]["work_unit_id"] == "WU-ESC"
    assert report["risk_escalations"][0]["new_state"] == "forbidden"

    assert len(report["anomalies"]["fencing_reassignments"]) == 1
    assert report["anomalies"]["fencing_reassignments"][0]["work_unit_id"] == "WU-DONE"
    assert report["anomalies"]["fencing_reassignments"][0]["superseded_by"] == "LEASE-REPORT-DONE-2"

    stop_events = [
        e
        for e in report["anomalies"]["blocker_events"]
        if (e["details"] or {}).get("stop_condition") == "repeated_systemic_failure"
    ]
    assert len(stop_events) == 1


def test_record_worker_heartbeat_succeeds_on_current_epoch(run_workspace: Workspace) -> None:
    """Orchestrator prerequisite — nothing previously refreshed heartbeat_at at all."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-HB-001", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-HB-1", run_id="RUN-HB-001", work_unit_id="WU-A", worker_id="w1")
    )
    lease_path = run_workspace.ai_team / "runs" / "leases" / "LEASE-HB-1.yaml"
    before = yaml.safe_load(lease_path.read_text(encoding="utf-8"))["heartbeat_at"]

    receipt, exit_code = gateway.execute_command(
        _record_heartbeat("LEASE-HB-1", run_id="RUN-HB-001", epoch=1)
    )
    assert exit_code == 0
    after = yaml.safe_load(lease_path.read_text(encoding="utf-8"))["heartbeat_at"]
    assert after != before


def test_record_worker_heartbeat_rejects_stale_epoch(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_open_run("RUN-HB-002", work_unit_ids=["WU-A"]))
    gateway.execute_command(
        _acquire_lease("LEASE-HB-2", run_id="RUN-HB-002", work_unit_id="WU-A", worker_id="w1")
    )
    _expire_lease_heartbeat(run_workspace, "LEASE-HB-2")
    gateway.execute_command(
        _acquire_lease("LEASE-HB-3", run_id="RUN-HB-002", work_unit_id="WU-A", worker_id="w2")
    )

    receipt, exit_code = gateway.execute_command(
        _record_heartbeat("LEASE-HB-2", run_id="RUN-HB-002", epoch=1)
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


# --- Mission artifacts + independent challenge (Document 6 §6) -------------


def _mission_contract_content(**overrides) -> dict:
    content = {
        "problem": "operators must approve every unattended decision by hand",
        "users": ["operator"],
        "observable_objective": "reduce manual approvals without losing safety",
        "scope_include": ["decision-menu automation"],
        "scope_exclude": ["production deploys"],
        "business_rules": ["never bypass gate decisions"],
        "invariants": ["human stays in control of irreversible actions"],
    }
    content.update(overrides)
    return content


def _register_mission_artifact(
    artifact_id: str,
    *,
    kind: str = "mission_contract",
    content: dict | None = None,
    role_id: str = "product-analyst",
) -> dict:
    return _envelope(
        "RegisterMissionArtifact",
        target={"kind": "mission_artifact", "id": artifact_id},
        payload={
            "id": artifact_id,
            "kind": kind,
            "content": content if content is not None else _mission_contract_content(),
        },
        key=f"register-artifact-{artifact_id}",
        role_id=role_id,
    )


def _challenge_mission_artifact(
    artifact_id: str,
    *,
    expected_revision: int,
    outcome: str = "approved",
    findings: list[str] | None = None,
    role_id: str = "auditor",
) -> dict:
    return _envelope(
        "RecordMissionArtifactChallenge",
        target={
            "kind": "mission_artifact",
            "id": artifact_id,
            "expected_revision": expected_revision,
        },
        payload={"outcome": outcome, "findings": findings or []},
        key=f"challenge-artifact-{artifact_id}-{expected_revision}-{outcome}",
        role_id=role_id,
    )


def test_register_mission_artifact_via_gateway(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(_register_mission_artifact("MA-001"))
    assert exit_code == 0
    document = json.loads(
        (run_workspace.ai_team / "mission-artifacts" / "MA-001.json").read_text(encoding="utf-8")
    )
    assert document["authored_by_role"] == "product-analyst"
    assert document["challenge_status"] == "pending"
    assert document["revision"] == 1


def test_register_mission_artifact_rejects_incomplete_content(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _register_mission_artifact("MA-BAD", content={"problem": "incomplete on purpose"})
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert not (run_workspace.ai_team / "mission-artifacts" / "MA-BAD.json").exists()


def test_challenge_mission_artifact_approves_via_independent_role(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_register_mission_artifact("MA-002"))
    receipt, exit_code = gateway.execute_command(
        _challenge_mission_artifact("MA-002", expected_revision=1, findings=["looks solid"])
    )
    assert exit_code == 0
    document = json.loads(
        (run_workspace.ai_team / "mission-artifacts" / "MA-002.json").read_text(encoding="utf-8")
    )
    assert document["challenge_status"] == "approved"
    assert document["challenged_by_role"] == "auditor"
    assert document["revision"] == 2


def test_challenge_mission_artifact_rejects_author_role_at_the_authorization_layer(
    run_workspace: Workspace,
) -> None:
    """Document 6 §6.2 — product-analyst (the author role) has no grant to challenge at all;
    role separation is enforced before the handler's own author/reviewer check ever runs."""
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_register_mission_artifact("MA-003"))
    receipt, exit_code = gateway.execute_command(
        _challenge_mission_artifact("MA-003", expected_revision=1, role_id="product-analyst")
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value
    document = json.loads(
        (run_workspace.ai_team / "mission-artifacts" / "MA-003.json").read_text(encoding="utf-8")
    )
    assert document["challenge_status"] == "pending"


def test_can_challenge_rejects_same_role_as_defense_in_depth() -> None:
    """Direct unit test of the handler's own guard (`handle_record_mission_artifact_challenge`),
    independent of which roles happen to hold which command grants today."""
    from governed_ai.core.domain.run.mission_artifact import can_challenge

    assert can_challenge(authored_by_role="auditor", challenger_role="product-analyst") is True
    assert can_challenge(authored_by_role="auditor", challenger_role="auditor") is False


def test_challenge_mission_artifact_rejects_stale_revision(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_register_mission_artifact("MA-004"))
    gateway.execute_command(_challenge_mission_artifact("MA-004", expected_revision=1))
    receipt, exit_code = gateway.execute_command(
        _challenge_mission_artifact("MA-004", expected_revision=1, outcome="changes_requested")
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_issue_grant_with_approved_mission_artifacts_records_hash(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_register_mission_artifact("MA-GRANT-1"))
    gateway.execute_command(_challenge_mission_artifact("MA-GRANT-1", expected_revision=1))

    receipt, exit_code = gateway.execute_command(
        _issue_grant(
            "GRANT-MISSION-001", work_unit_ids=["WU-A"], mission_artifact_ids=["MA-GRANT-1"]
        )
    )
    assert exit_code == 0
    document = json.loads(
        (run_workspace.ai_team / "run-authorization-grants" / "GRANT-MISSION-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["mission_artifact_ids"] == ["MA-GRANT-1"]
    assert document["mission_contract_hash"].startswith("sha256:")


def test_issue_grant_rejects_unapproved_mission_artifact(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(_register_mission_artifact("MA-GRANT-2"))

    receipt, exit_code = gateway.execute_command(
        _issue_grant(
            "GRANT-MISSION-002", work_unit_ids=["WU-A"], mission_artifact_ids=["MA-GRANT-2"]
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    assert not (
        run_workspace.ai_team / "run-authorization-grants" / "GRANT-MISSION-002.json"
    ).exists()


def test_issue_grant_rejects_unknown_mission_artifact(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    receipt, exit_code = gateway.execute_command(
        _issue_grant(
            "GRANT-MISSION-003", work_unit_ids=["WU-A"], mission_artifact_ids=["MA-MISSING"]
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.NOT_FOUND.value


# --- Definition of Unattended-Ready dashboard (Document 6 §6.3) ------------


def test_unattended_readiness_requires_preset(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    with pytest.raises(GatewayError) as exc_info:
        gateway.query("unattended-readiness", args={"work_unit_ids": ["WU-A"], "grant_id": "G"})
    assert exc_info.value.code == ErrorCode.INVALID_SCHEMA


def test_unattended_readiness_unknown_grant(run_workspace: Workspace) -> None:
    gateway = CommandGateway(run_workspace)
    with pytest.raises(GatewayError) as exc_info:
        gateway.query(
            "unattended-readiness",
            args={
                "preset": "unattended_conservative",
                "work_unit_ids": ["WU-A"],
                "grant_id": "GRANT-DOES-NOT-EXIST",
            },
        )
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_unattended_readiness_flags_missing_work_unit_and_budget(
    run_workspace: Workspace,
) -> None:
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant("GRANT-READY-1", work_unit_ids=["WU-GHOST"], maximum_uses=1)
    )
    result = gateway.query(
        "unattended-readiness",
        args={
            "preset": "unattended_conservative",
            "work_unit_ids": ["WU-GHOST"],
            "grant_id": "GRANT-READY-1",
        },
    )
    report = result["data"]
    assert report["ready"] is False
    assert any("work unit not found" in gap for gap in report["gaps"])
    assert any("no explicit budget" in gap for gap in report["gaps"])
    assert any(
        "mission artifact of kind 'mission_contract'" in gap for gap in report["gaps"]
    )


def test_unattended_readiness_conservative_preset_passes_with_minimal_artifacts(
    run_workspace: Workspace,
) -> None:
    _seed_work_unit(run_workspace, "WU-READY-1", status="ready", scope_include=["src/"])
    gateway = CommandGateway(run_workspace)
    for artifact_id, kind in (
        ("MA-READY-CONTRACT", "mission_contract"),
        ("MA-READY-ENV", "execution_envelope"),
        ("MA-READY-DELIVERY", "delivery_contract"),
    ):
        content = {
            "mission_contract": _mission_contract_content(),
            "execution_envelope": {
                "environments": ["development"],
                "network": "deny_by_default",
                "allowed_dependencies": [],
                "accessible_secrets": [],
                "allowed_paths": ["src/"],
                "allowed_commands": [],
                "budgets": {"maximum_duration_hours": 8},
            },
            "delivery_contract": {
                "deliverable_definition": "a merged, green working branch",
                "rollback_criteria": ["revert the integration merge"],
                "required_evidence": ["ci_run_ok"],
            },
        }[kind]
        gateway.execute_command(_register_mission_artifact(artifact_id, kind=kind, content=content))
        gateway.execute_command(_challenge_mission_artifact(artifact_id, expected_revision=1))

    gateway.execute_command(
        _issue_grant(
            "GRANT-READY-2",
            work_unit_ids=["WU-READY-1"],
            mission_artifact_ids=["MA-READY-CONTRACT", "MA-READY-ENV", "MA-READY-DELIVERY"],
        )
    )
    # A grant issued through this handler never carries an explicit budget by
    # default in this test helper — patch it in directly to isolate the
    # dimension this test is actually about.
    grant_path = run_workspace.ai_team / "run-authorization-grants" / "GRANT-READY-2.json"
    document = json.loads(grant_path.read_text(encoding="utf-8"))
    document["maximum_duration_hours"] = 8
    grant_path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    result = gateway.query(
        "unattended-readiness",
        args={
            "preset": "unattended_conservative",
            "work_unit_ids": ["WU-READY-1"],
            "grant_id": "GRANT-READY-2",
            "execution_ceilings_by_work_unit": {"WU-READY-1": {}},
        },
    )
    report = result["data"]
    assert report["gaps"] == []
    assert report["ready"] is True


def test_unattended_readiness_extended_preset_requires_acceptance_oracle(
    run_workspace: Workspace,
) -> None:
    _seed_work_unit(run_workspace, "WU-READY-2", status="ready", scope_include=["src/"])
    gateway = CommandGateway(run_workspace)
    gateway.execute_command(
        _issue_grant("GRANT-READY-3", work_unit_ids=["WU-READY-2"], mission_artifact_ids=[])
    )
    result = gateway.query(
        "unattended-readiness",
        args={
            "preset": "unattended_extended",
            "work_unit_ids": ["WU-READY-2"],
            "grant_id": "GRANT-READY-3",
            "execution_ceilings_by_work_unit": {"WU-READY-2": {}},
        },
    )
    report = result["data"]
    assert any(
        "mission artifact of kind 'acceptance_oracle'" in gap for gap in report["gaps"]
    )
