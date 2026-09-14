"""Unit and integration tests for the Supervisor Daemon (DAEMON-AC-*)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from governed_ai.compat.datetime import UTC, datetime, timedelta
from governed_ai.core.domain.run.autonomy_policy import is_unattended_preset
from governed_ai.core.domain.run.path_policy import sanitize_allowed_paths
from governed_ai.core.supervisor import journal, queue, registry
from governed_ai.core.supervisor.daemon import SupervisorDaemon
from governed_ai.core.supervisor.hard_stops import HARD_STOPS
from governed_ai.core.supervisor.instance_lock import (
    InstanceLockError,
    acquire_instance_lock,
    read_instance_status,
)
from governed_ai.core.supervisor.paths import ensure_supervisor_layout, instance_lock_path
from governed_ai.core.supervisor.process import terminate_process, write_process_record
from governed_ai.core.supervisor.protocol import WorkerAttemptState, can_transition
from governed_ai.core.supervisor.reconcile import choose_action, execute_action, observe_run
from governed_ai.core.supervisor.recovery import (
    boundary_recovery_start_shas,
    grant_has_remaining_use,
    recover,
)
from governed_ai.core.supervisor.status import build_doctor, build_status
from governed_ai.core.workspace import Workspace


def _workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    (ai_team / "runs").mkdir(parents=True)
    (ai_team / "work-units").mkdir(parents=True)
    (ai_team / "state").mkdir(parents=True)
    (tmp_path / "scripts" / "ai-team").mkdir(parents=True)
    # Minimal profile so Workspace helpers that read it do not explode if used.
    (ai_team / "project-profile.yaml").write_text(
        "project:\n  id: test\n  repository_kind: client_project\n",
        encoding="utf-8",
    )
    ensure_supervisor_layout(ai_team)
    return Workspace.from_root(tmp_path)


def _write_run(ai_team: Path, run_id: str, **fields: object) -> dict:
    now = datetime.now(UTC)
    document = {
        "id": run_id,
        "status": "active",
        "revision": 1,
        "created_at": (now - timedelta(minutes=1)).isoformat(),
        "opened_at": (now - timedelta(minutes=1)).isoformat(),
        "work_unit_ids": ["WU-A"],
        "autonomy_preset": "unattended_conservative",
        "run_authorization_grant_id": "GRANT-1",
        "leases_by_work_unit": {},
        "effective_autonomy_policy": {"execution": {"stalled_after_minutes": 15}},
        **fields,
    }
    path = ai_team / "runs" / f"{run_id}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return document


def test_concurrent_lock_acquisition_rejects_second(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = acquire_instance_lock(workspace.ai_team)
    try:
        raised = False
        try:
            acquire_instance_lock(workspace.ai_team)
        except InstanceLockError:
            raised = True
        assert raised
    finally:
        first.release()


def test_stale_pid_lock_can_be_reclaimed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = instance_lock_path(workspace.ai_team)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = {
        "schema_version": 1,
        "instance_id": "old",
        "token": "tok",
        "pid": 999_999_999,
        "started_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "heartbeat_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "workspace_id": str(workspace.ai_team.resolve()),
    }
    path.write_text(json.dumps(stale), encoding="utf-8")
    lock = acquire_instance_lock(
        workspace.ai_team,
        pid_is_alive=lambda _pid: False,
    )
    assert lock.instance_id != "old"
    lock.release()


def test_live_pid_lock_is_never_reclaimed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = instance_lock_path(workspace.ai_team)
    path.parent.mkdir(parents=True, exist_ok=True)
    live = {
        "schema_version": 1,
        "instance_id": "live",
        "token": "tok",
        "pid": 42,
        "started_at": datetime.now(UTC).isoformat(),
        "heartbeat_at": datetime.now(UTC).isoformat(),
        "workspace_id": str(workspace.ai_team.resolve()),
    }
    path.write_text(json.dumps(live), encoding="utf-8")
    try:
        acquire_instance_lock(
            workspace.ai_team,
            pid_is_alive=lambda pid: pid == 42,
            process_start_time=lambda _pid: None,
        )
        assert False, "expected InstanceLockError"
    except InstanceLockError:
        pass


def test_pid_reuse_is_detected_via_start_time(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = instance_lock_path(workspace.ai_team)
    path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC) - timedelta(hours=2)
    document = {
        "schema_version": 1,
        "instance_id": "reused",
        "token": "tok",
        "pid": 7,
        "started_at": started.isoformat(),
        "heartbeat_at": (started + timedelta(minutes=1)).isoformat(),
        "workspace_id": str(workspace.ai_team.resolve()),
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    # OS reports a process start AFTER the lock started_at → PID reused.
    lock = acquire_instance_lock(
        workspace.ai_team,
        pid_is_alive=lambda pid: pid == 7,
        process_start_time=lambda _pid: started.timestamp() + 3600,
    )
    assert lock.instance_id != "reused"
    lock.release()


def test_daemon_restart_reconstructs_from_registry(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-1")
    (workspace.ai_team / "work-units" / "WU-A.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-A",
                "status": "in_progress",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    registry.register_run(workspace.ai_team, "RUN-1", workers=1)

    class _FakeHandle:
        pid = 424242

    def _fake_launch(_root: Path, _run_id: str, _workers: int) -> _FakeHandle:
        return _FakeHandle()

    alive_pids: set[int] = set()

    def _alive(pid: int) -> bool:
        return pid in alive_pids

    def _process_alive(_ai: Path, _run: str) -> bool:
        record = None
        try:
            from governed_ai.core.supervisor.process import read_process_record

            record = read_process_record(_ai, _run)
        except Exception:  # noqa: BLE001
            record = None
        if not record:
            return False
        return _alive(int(record.get("pid") or 0))

    daemon = SupervisorDaemon(workspace, interval_seconds=0.1)
    daemon.acquire()
    try:
        with (
            patch(
                "governed_ai.core.supervisor.process.launch_orchestrator",
                _fake_launch,
            ),
            patch(
                "governed_ai.core.supervisor.process.default_pid_is_alive",
                _alive,
            ),
            patch(
                "governed_ai.core.supervisor.reconcile.process_is_alive",
                _process_alive,
            ),
            patch(
                "governed_ai.core.supervisor.reconcile.legacy_orchestrator_process_alive",
                lambda _ai, _run: False,
            ),
        ):
            results = daemon.reconcile_once()
            # Process record now exists with fake pid — mark it live for restart.
            alive_pids.add(424242)
        assert results and results[0]["run_id"] == "RUN-1"
        assert results[0]["result"].get("outcome") == "started"
    finally:
        daemon.shutdown()
    # Simulate abrupt kill: lock gone, registry + process record remain.
    status = read_instance_status(workspace.ai_team)
    assert status["state"] == "stopped"
    daemon2 = SupervisorDaemon(workspace, interval_seconds=0.1)
    daemon2.acquire()
    try:
        assert len(registry.list_registered_runs(workspace.ai_team)) == 1
        with (
            patch(
                "governed_ai.core.supervisor.process.launch_orchestrator",
                _fake_launch,
            ),
            patch(
                "governed_ai.core.supervisor.process.default_pid_is_alive",
                _alive,
            ),
            patch(
                "governed_ai.core.supervisor.reconcile.process_is_alive",
                _process_alive,
            ),
            patch(
                "governed_ai.core.supervisor.reconcile.legacy_orchestrator_process_alive",
                lambda _ai, _run: False,
            ),
        ):
            second = daemon2.reconcile_once()
        # Alive managed process → no second start / no concurrent attempt.
        assert second[0]["plan"]["action"] == "noop_healthy"
        starts = [
            item
            for item in queue.list_items(workspace.ai_team)
            if item.get("kind") == "start_orchestrator" and item.get("state") != "completed"
        ]
        assert starts == []
    finally:
        daemon2.shutdown()


def test_stalled_no_progress_action(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    old = (datetime.now(UTC) - timedelta(minutes=40)).isoformat()
    _write_run(
        workspace.ai_team,
        "RUN-STALL",
        created_at=old,
        opened_at=old,
        effective_autonomy_policy={"execution": {"stalled_after_minutes": 15}},
    )
    (workspace.ai_team / "work-units" / "WU-A.yaml").write_text(
        yaml.safe_dump({"id": "WU-A", "status": "in_progress", "updated_at": old}),
        encoding="utf-8",
    )
    observation = observe_run(workspace, "RUN-STALL")
    plan = choose_action(observation, {"max_recoveries": 3})
    assert plan["action"] == "recover_stalled"
    assert observation["progress"]["state"] == "stalled_no_progress"


def test_missing_process_is_orphan_recovery(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-ORPHAN")
    write_process_record(
        workspace.ai_team,
        "RUN-ORPHAN",
        {
            "pid": 999_999_998,
            "worker_attempt_state": WorkerAttemptState.RUNNING.value,
            "lease_epoch": 1,
        },
    )
    observation = observe_run(workspace, "RUN-ORPHAN")
    # Force dead PID observation
    observation["process_alive"] = False
    plan = choose_action(observation, {})
    assert plan["action"] == "recover_orphan"


def test_queue_epoch_fencing_rejects_stale_complete(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    item = queue.enqueue(workspace.ai_team, run_id="RUN-1", kind="work")
    leased = queue.lease_next(workspace.ai_team, worker_id="w1")
    assert leased is not None
    # Bump epoch by reclaiming and re-leasing.
    path = workspace.ai_team / "supervisor" / "queue" / f"{leased['id']}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["lease_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")
    reclaimed = queue.reclaim_expired_leases(workspace.ai_team)
    assert reclaimed
    leased2 = queue.lease_next(workspace.ai_team, worker_id="w2")
    assert leased2 is not None
    assert int(leased2["lease_epoch"]) > int(leased["lease_epoch"])
    try:
        queue.complete(
            workspace.ai_team,
            str(item["id"]),
            lease_id=str(leased["lease_id"]),
            lease_epoch=int(leased["lease_epoch"]),
        )
        assert False, "stale epoch must be refused"
    except PermissionError:
        pass


def test_double_dispatch_dedupe_key(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = queue.enqueue(
        workspace.ai_team, run_id="RUN-1", kind="start", dedupe_key="start:RUN-1:1"
    )
    second = queue.enqueue(
        workspace.ai_team, run_id="RUN-1", kind="start", dedupe_key="start:RUN-1:1"
    )
    assert first["id"] == second["id"]


def test_cancel_process_after_run_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-CLOSE", status="completed")
    write_process_record(
        workspace.ai_team,
        "RUN-CLOSE",
        {"pid": os.getpid(), "lease_epoch": 1, "worker_attempt_state": "running"},
    )
    # Do not actually kill our pytest process — use a fake dead pid path via terminate on missing.
    write_process_record(
        workspace.ai_team,
        "RUN-CLOSE",
        {"pid": 999_999_997, "lease_epoch": 1, "worker_attempt_state": "running"},
    )
    observation = observe_run(workspace, "RUN-CLOSE")
    observation["process_alive"] = True  # force cancel plan
    plan = choose_action(observation, {})
    assert plan["action"] == "cancel_process"
    result = terminate_process(workspace.ai_team, "RUN-CLOSE", expected_epoch=1)
    assert result["outcome"] in {"already_gone", "cancelled", "still_alive"}


def test_stale_epoch_termination_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    write_process_record(
        workspace.ai_team,
        "RUN-E",
        {"pid": 999_999_996, "lease_epoch": 3, "worker_attempt_state": "running"},
    )
    result = terminate_process(workspace.ai_team, "RUN-E", expected_epoch=1)
    assert result["outcome"] == "fencing_conflict"


def test_corrupt_journal_event_isolated(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    events = workspace.ai_team / "supervisor" / "journal" / "events"
    events.mkdir(parents=True, exist_ok=True)
    (events / "00000001-bad.json").write_text("{not-json", encoding="utf-8")
    journal.append_event(
        workspace.ai_team,
        instance_id="i1",
        event_type="ok",
        run_id="RUN-1",
        payload={"x": 1},
    )
    loaded = journal.iter_events(workspace.ai_team, after_sequence=0)
    assert any(item.get("event_type") == "ok" for item in loaded)
    alerts = journal.load_alerts(workspace.ai_team)
    assert any(item.get("code") == "corrupt_journal_event" for item in alerts)


def test_dead_letter_after_max_attempts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    item = queue.enqueue(
        workspace.ai_team, run_id="RUN-1", kind="work", max_attempts=1
    )
    leased = queue.lease_next(workspace.ai_team, worker_id="w1")
    assert leased is not None
    failed = queue.fail(
        workspace.ai_team,
        str(item["id"]),
        lease_id=str(leased["lease_id"]),
        lease_epoch=int(leased["lease_epoch"]),
        error={"code": "boom", "message": "fail"},
    )
    assert failed["state"] == "dead_letter"


def test_grant_without_remaining_use(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    grants = workspace.ai_team / "run-authorization-grants"
    grants.mkdir(parents=True)
    (grants / "GRANT-X.json").write_text(
        json.dumps(
            {
                "id": "GRANT-X",
                "status": "exhausted",
                "uses_count": 3,
                "max_uses": 3,
            }
        ),
        encoding="utf-8",
    )
    ok, reason = grant_has_remaining_use(workspace, "GRANT-X")
    assert not ok
    assert "exhausted" in reason or "status" in reason


def test_custom_preset_is_unattended(tmp_path: Path) -> None:
    assert is_unattended_preset("custom")
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-CUSTOM", autonomy_preset="custom")
    observation = observe_run(workspace, "RUN-CUSTOM")
    plan = choose_action(observation, {})
    assert plan["action"] != "noop_supervised"


def test_hard_stops_not_auto_recovered(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for stop in sorted(HARD_STOPS):
        _write_run(workspace.ai_team, "RUN-HS", stop_condition=stop)
        observation = observe_run(workspace, "RUN-HS")
        plan = choose_action(observation, {})
        # Active run with hard stop recorded still active is unusual; choose_action
        # checks stop_condition for hard stops when active.
        assert plan["action"] == "needs_human", stop


def test_supervisor_paths_are_control_plane_only() -> None:
    sanitized = sanitize_allowed_paths([".ai-team/supervisor/**", "src/**"])
    assert ".ai-team/supervisor/**" not in sanitized
    assert "src/**" in sanitized


def test_status_and_doctor_json_progress_signal(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-1")
    registry.register_run(workspace.ai_team, "RUN-1")
    status = build_status(workspace)
    assert "progressing" in status
    assert "daemon" in status
    assert isinstance(status["runs"], list)
    doctor = build_doctor(workspace)
    assert "doctor" in doctor
    assert "ok" in doctor["doctor"]


def test_graceful_shutdown_releases_lock(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    daemon = SupervisorDaemon(workspace, interval_seconds=0.05)
    daemon.acquire()
    assert read_instance_status(workspace.ai_team)["state"] == "running"
    daemon.shutdown()
    assert read_instance_status(workspace.ai_team)["state"] == "stopped"


def test_worker_protocol_transitions() -> None:
    assert can_transition(WorkerAttemptState.QUEUED, WorkerAttemptState.LEASED)
    assert can_transition(WorkerAttemptState.RUNNING, WorkerAttemptState.ORPHANED)
    assert not can_transition(WorkerAttemptState.SUCCEEDED, WorkerAttemptState.RUNNING)


def test_concurrent_starters_only_one_wins(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    results: list[str] = []
    errors: list[str] = []

    def _starter() -> None:
        try:
            lock = acquire_instance_lock(workspace.ai_team)
            results.append(lock.instance_id)
            # Hold briefly so the loser observes a live lock.
            threading.Event().wait(0.2)
            lock.release()
        except InstanceLockError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=_starter) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 1
    assert len(errors) == 1


def test_max_recoveries_dead_letter_via_reconcile(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-MAX", status="failed", stop_condition="stalled_no_progress")
    registry.register_run(workspace.ai_team, "RUN-MAX", max_recoveries=1)
    recovery_dir = workspace.ai_team / "runs" / "recovery"
    recovery_dir.mkdir(parents=True)
    (recovery_dir / "RUN-MAX.json").write_text(
        json.dumps({"attempts": 1, "outcome": "recovered"}),
        encoding="utf-8",
    )
    result = execute_action(
        workspace,
        instance_id="inst",
        run_id="RUN-MAX",
        entry={"workers": 1, "max_recoveries": 1},
        observation=observe_run(workspace, "RUN-MAX"),
        plan={"action": "recover_orphan", "reason": "test"},
    )
    assert result["outcome"] in {"dead_letter", "needs_human"}
    if result["outcome"] == "dead_letter":
        assert any(
            item.get("state") == "dead_letter"
            for item in queue.list_items(workspace.ai_team, include_dead_letter=True)
        )


def test_boundary_sha_extracted_for_recovery(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    attempts = workspace.ai_team / "runs" / "execution-attempts"
    attempts.mkdir(parents=True)
    sha = "a" * 40
    (attempts / "ATT-1.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "ATT-1",
                "run_id": "RUN-B",
                "work_unit_id": "WU-A",
                "summary": "Execution boundary: out of workspace write",
                "ended_at": "2026-01-01T00:00:00+00:00",
                "workspace": {"base_sha": sha},
            }
        ),
        encoding="utf-8",
    )
    mapped = boundary_recovery_start_shas(workspace, "RUN-B")
    assert mapped == {"WU-A": sha}


def test_out_of_scope_recovery_without_sha_needs_human(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(
        workspace.ai_team,
        "RUN-OOS",
        status="failed",
        stop_condition="out_of_workspace_write",
        autonomy_preset="unattended_conservative",
    )
    result = recover(workspace, "RUN-OOS", max_recoveries=3, launch=False, workers=1)
    assert result["outcome"] == "needs_human"
    assert "SHA" in result["reason"] or "sha" in result["reason"].lower()


def test_recovery_uses_command_gateway(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(
        workspace.ai_team,
        "RUN-GW",
        status="failed",
        stop_condition="orchestrator_process_failure",
        autonomy_preset="custom",
    )
    grants = workspace.ai_team / "run-authorization-grants"
    grants.mkdir(parents=True)
    (grants / "GRANT-1.json").write_text(
        json.dumps({"id": "GRANT-1", "status": "active", "uses_count": 0, "max_uses": 3}),
        encoding="utf-8",
    )
    (workspace.ai_team / "work-units" / "WU-A.yaml").write_text(
        yaml.safe_dump({"id": "WU-A", "status": "ready", "revision": 1}),
        encoding="utf-8",
    )
    mock_gateway = MagicMock()
    mock_gateway.execute_command.return_value = (
        {"errors": [], "result": {"id": "RUN-RECOVERY"}},
        0,
    )
    with patch(
        "governed_ai.core.supervisor.recovery.CommandGateway",
        return_value=mock_gateway,
    ):
        with patch(
            "governed_ai.core.supervisor.recovery.dispatch_notifications",
            lambda *_a, **_k: None,
        ):
            result = recover(workspace, "RUN-GW", max_recoveries=3, launch=False, workers=1)
    assert mock_gateway.execute_command.called
    types = [
        call.args[0].get("type")
        for call in mock_gateway.execute_command.call_args_list
    ]
    assert "OpenRun" in types
    assert result["outcome"] in {"recovered", "needs_human"}


def test_exhausted_grant_blocks_recovery_open(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(
        workspace.ai_team,
        "RUN-EX",
        status="failed",
        stop_condition="orchestrator_process_failure",
    )
    grants = workspace.ai_team / "run-authorization-grants"
    grants.mkdir(parents=True)
    (grants / "GRANT-1.json").write_text(
        json.dumps({"id": "GRANT-1", "status": "exhausted", "uses_count": 3, "max_uses": 3}),
        encoding="utf-8",
    )
    result = recover(workspace, "RUN-EX", max_recoveries=3, launch=False, workers=1)
    assert result["outcome"] == "needs_human"
    assert "grant" in result["reason"].lower()


def test_shutdown_journals_active_attempts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write_run(workspace.ai_team, "RUN-S")
    registry.register_run(workspace.ai_team, "RUN-S")
    write_process_record(
        workspace.ai_team,
        "RUN-S",
        {
            "pid": 12345,
            "worker_attempt_state": WorkerAttemptState.RUNNING.value,
            "lease_epoch": 2,
        },
    )
    daemon = SupervisorDaemon(workspace, interval_seconds=0.05)
    daemon.acquire()
    daemon.shutdown()
    events = journal.iter_events(workspace.ai_team, after_sequence=0)
    stopping = [item for item in events if item.get("event_type") == "daemon_stopping"]
    assert stopping
    assert stopping[-1]["payload"].get("reattach_on_restart") is True
    assert any(item.get("run_id") == "RUN-S" for item in stopping[-1]["payload"]["active_attempts"])


def test_expired_queue_lease_reclaimed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    item = queue.enqueue(workspace.ai_team, run_id="RUN-1", kind="work")
    leased = queue.lease_next(workspace.ai_team, worker_id="w1", visibility_timeout_seconds=1.0)
    assert leased is not None
    path = workspace.ai_team / "supervisor" / "queue" / f"{item['id']}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["lease_expires_at"] = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")
    reclaimed = queue.reclaim_expired_leases(workspace.ai_team)
    assert len(reclaimed) == 1
    assert reclaimed[0]["worker_attempt_state"] == WorkerAttemptState.ORPHANED.value


def test_wip_sha_preserved_in_recovery_payload(tmp_path: Path) -> None:
    """Boundary recovery carries the pre-violation SHA; WIP commits stay on the branch."""
    workspace = _workspace(tmp_path)
    sha = "b" * 40
    attempts = workspace.ai_team / "runs" / "execution-attempts"
    attempts.mkdir(parents=True)
    (attempts / "ATT-WIP.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "ATT-WIP",
                "run_id": "RUN-WIP",
                "work_unit_id": "WU-A",
                "summary": "Execution boundary: forbidden path",
                "ended_at": "2026-01-02T00:00:00+00:00",
                "workspace": {"base_sha": sha},
            }
        ),
        encoding="utf-8",
    )
    _write_run(
        workspace.ai_team,
        "RUN-WIP",
        status="failed",
        stop_condition="out_of_workspace_write",
    )
    grants = workspace.ai_team / "run-authorization-grants"
    grants.mkdir(parents=True)
    (grants / "GRANT-1.json").write_text(
        json.dumps({"id": "GRANT-1", "status": "active", "uses_count": 0, "max_uses": 5}),
        encoding="utf-8",
    )
    (workspace.ai_team / "work-units" / "WU-A.yaml").write_text(
        yaml.safe_dump({"id": "WU-A", "status": "ready", "revision": 1}),
        encoding="utf-8",
    )
    captured: list[dict] = []

    def _execute(envelope: dict) -> tuple[dict, int]:
        captured.append(envelope)
        if envelope.get("type") == "OpenRun":
            return ({"errors": []}, 0)
        return ({"errors": []}, 0)

    mock_gateway = MagicMock()
    mock_gateway.execute_command.side_effect = lambda envelope: _execute(envelope)
    with patch(
        "governed_ai.core.supervisor.recovery.CommandGateway",
        return_value=mock_gateway,
    ):
        with patch(
            "governed_ai.core.supervisor.recovery.dispatch_notifications",
            lambda *_a, **_k: None,
        ):
            result = recover(workspace, "RUN-WIP", max_recoveries=3, launch=False, workers=1)
    open_payloads = [item["payload"] for item in captured if item.get("type") == "OpenRun"]
    assert open_payloads
    assert open_payloads[0].get("recovery_start_shas_by_work_unit") == {"WU-A": sha}
    assert result["outcome"] == "recovered"
