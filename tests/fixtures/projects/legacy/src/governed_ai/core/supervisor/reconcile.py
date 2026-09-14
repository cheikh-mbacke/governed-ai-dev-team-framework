"""Single-run reconciliation: desired vs observed → one idempotent action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.domain.run.autonomy_policy import is_unattended_preset
from governed_ai.core.orchestrator.progress import evaluate_run_progress
from governed_ai.core.supervisor import journal, queue, registry
from governed_ai.core.supervisor.hard_stops import HARD_STOPS
from governed_ai.core.supervisor.process import (
    legacy_orchestrator_process_alive,
    process_is_alive,
    read_process_record,
    start_orchestrator_process,
    terminate_process,
)
from governed_ai.core.supervisor.protocol import WorkerAttemptState
from governed_ai.core.supervisor.recovery import grant_has_remaining_use, recover
from governed_ai.core.workspace import Workspace


def _read_run(ai_team: Path, run_id: str) -> dict[str, Any] | None:
    path = ai_team / "runs" / f"{run_id}.yaml"
    if not path.is_file():
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    return document if isinstance(document, dict) else None


def observe_run(workspace: Workspace, run_id: str) -> dict[str, Any]:
    run = _read_run(workspace.ai_team, run_id)
    if run is None:
        return {
            "run_id": run_id,
            "run_status": "missing",
            "progress": {"state": "unknown"},
            "process_alive": False,
            "legacy_process_alive": False,
            "process": None,
        }
    progress = evaluate_run_progress(workspace.ai_team, run)
    process = read_process_record(workspace.ai_team, run_id)
    alive = process_is_alive(workspace.ai_team, run_id)
    legacy_alive = legacy_orchestrator_process_alive(workspace.ai_team, run_id)
    leases = run.get("leases_by_work_unit") or {}
    active_lease = next(iter(leases.values()), None) if leases else None
    return {
        "run_id": run_id,
        "run_status": run.get("status"),
        "stop_condition": run.get("stop_condition"),
        "autonomy_preset": run.get("autonomy_preset"),
        "revision": run.get("revision"),
        "work_unit_ids": list(run.get("work_unit_ids") or []),
        "progress": progress,
        "process_alive": alive or legacy_alive,
        "legacy_process_alive": legacy_alive,
        "process": process,
        "current_lease": active_lease,
        "recovery_count": int(run.get("recovery_attempt_number") or 0),
        "grant_id": run.get("run_authorization_grant_id"),
    }


def choose_action(observation: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Return exactly one planned action for this reconcile cycle."""
    run_status = observation.get("run_status")
    if run_status in {None, "missing"}:
        return {
            "action": "needs_human",
            "reason": "run document missing",
            "wait_reason": "missing_run",
        }
    if run_status != "active":
        if observation.get("process_alive"):
            return {
                "action": "cancel_process",
                "reason": "run no longer active",
                "wait_reason": None,
            }
        return {
            "action": "noop_terminal",
            "reason": f"run status={run_status}",
            "wait_reason": "terminal",
        }

    if not is_unattended_preset(observation.get("autonomy_preset")):
        return {
            "action": "noop_supervised",
            "reason": "supervised Run — daemon observes only",
            "wait_reason": "supervised_mode",
        }

    stop = str(observation.get("stop_condition") or "")
    if stop in HARD_STOPS:
        return {
            "action": "needs_human",
            "reason": f"hard stop: {stop}",
            "wait_reason": "hard_stop",
        }

    progress_state = (observation.get("progress") or {}).get("state")
    if progress_state == "stalled_no_progress":
        return {
            "action": "recover_stalled",
            "reason": "alive or idle without useful progress",
            "wait_reason": "stalled_no_progress",
        }

    if not observation.get("process_alive"):
        process = observation.get("process") or {}
        prior_state = process.get("worker_attempt_state")
        had_managed_process = bool(process.get("pid")) or prior_state in {
            WorkerAttemptState.STARTING.value,
            WorkerAttemptState.RUNNING.value,
        }
        if had_managed_process:
            return {
                "action": "recover_orphan",
                "reason": "orchestrator process missing after start",
                "wait_reason": "orphan_process",
            }
        return {
            "action": "start_orchestrator",
            "reason": "active Run without managed process",
            "wait_reason": None,
        }

    if observation.get("process_alive") and progress_state in {"working", "progressing"}:
        return {
            "action": "noop_healthy",
            "reason": "process alive with useful progress window",
            "wait_reason": None,
        }

    return {
        "action": "noop_healthy",
        "reason": "no corrective action required",
        "wait_reason": None,
    }


def execute_action(
    workspace: Workspace,
    *,
    instance_id: str,
    run_id: str,
    entry: dict[str, Any],
    observation: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    action = plan["action"]
    workers = int(entry.get("workers") or 1)
    max_recoveries = int(entry.get("max_recoveries") or 3)

    if action == "noop_healthy":
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="healthy",
            last_action=action,
            next_action="observe",
            wait_reason=None,
        )
        return {"outcome": "ok", "action": action}

    if action == "noop_terminal":
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="terminal",
            last_action=action,
            next_action="none",
            wait_reason="terminal",
        )
        return {"outcome": "ok", "action": action}

    if action == "noop_supervised":
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="supervised",
            last_action=action,
            next_action="observe",
            wait_reason="supervised_mode",
        )
        return {"outcome": "ok", "action": action}

    if action == "cancel_process":
        result = terminate_process(
            workspace.ai_team,
            run_id,
            grace_seconds=2.0,
            expected_epoch=(observation.get("process") or {}).get("lease_epoch"),
        )
        journal.append_event(
            workspace.ai_team,
            instance_id=instance_id,
            event_type="process_cancelled",
            run_id=run_id,
            payload={"result": result.get("outcome")},
        )
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="cancelled_process",
            last_action=action,
            next_action="observe",
            wait_reason="terminal",
        )
        return {"outcome": result.get("outcome"), "action": action, "detail": result}

    if action == "start_orchestrator":
        usable, grant_reason = grant_has_remaining_use(workspace, observation.get("grant_id"))
        # Starting an already-open Run does not consume a grant use; only recovery OpenRun does.
        # Still refuse if grant is revoked/expired as a safety signal for unattended work.
        if observation.get("grant_id") and grant_reason.startswith("grant status"):
            registry.update_run_entry(
                workspace.ai_team,
                run_id,
                status="needs_human",
                last_action=action,
                wait_reason=grant_reason,
            )
            return {"outcome": "needs_human", "action": action, "reason": grant_reason}
        epoch = int((observation.get("process") or {}).get("lease_epoch") or 0) + 1
        queue_item = queue.enqueue(
            workspace.ai_team,
            run_id=run_id,
            kind="start_orchestrator",
            dedupe_key=f"start:{run_id}:{epoch}",
            payload={"workers": workers, "lease_epoch": epoch},
        )
        leased = queue.lease_next(
            workspace.ai_team, worker_id=f"supervisor-{instance_id[:8]}"
        )
        if leased is None:
            leased = queue_item
        try:
            queue.acknowledge(
                workspace.ai_team,
                str(leased["id"]),
                lease_id=str(leased.get("lease_id") or "bootstrap"),
                lease_epoch=int(leased.get("lease_epoch") or epoch),
                worker_attempt_state=WorkerAttemptState.STARTING.value,
            )
        except (KeyError, PermissionError):
            pass
        process_doc = start_orchestrator_process(
            workspace.root,
            workspace.ai_team,
            run_id,
            workers=workers,
            lease_epoch=epoch,
        )
        try:
            queue.complete(
                workspace.ai_team,
                str(leased["id"]),
                lease_id=str(leased.get("lease_id") or "bootstrap"),
                lease_epoch=int(leased.get("lease_epoch") or epoch),
                worker_attempt_state=WorkerAttemptState.RUNNING.value,
                result={"pid": process_doc.get("pid")},
            )
        except (KeyError, PermissionError):
            pass
        journal.append_event(
            workspace.ai_team,
            instance_id=instance_id,
            event_type="orchestrator_started",
            run_id=run_id,
            payload={"pid": process_doc.get("pid"), "epoch": epoch},
        )
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="running",
            last_action=action,
            next_action="observe",
            active_pid=process_doc.get("pid"),
            lease_epoch=epoch,
        )
        return {"outcome": "started", "action": action, "process": process_doc}

    if action in {"recover_orphan", "recover_stalled"}:
        recovery = recover(
            workspace,
            run_id,
            max_recoveries=max_recoveries,
            launch=False,
            workers=workers,
        )
        journal.append_event(
            workspace.ai_team,
            instance_id=instance_id,
            event_type="recovery_attempt",
            run_id=run_id,
            payload={
                "outcome": recovery.get("outcome"),
                "new_run_id": recovery.get("new_run_id"),
                "reason": recovery.get("reason"),
            },
        )
        if recovery.get("outcome") == "recovered" and recovery.get("new_run_id"):
            new_run_id = str(recovery["new_run_id"])
            registry.unregister_run(workspace.ai_team, run_id)
            registry.register_run(
                workspace.ai_team,
                new_run_id,
                workers=workers,
                max_recoveries=max_recoveries,
                metadata={"recovered_from": run_id},
            )
            # Start the replacement Run's orchestrator in this same cycle owner.
            start_result = execute_action(
                workspace,
                instance_id=instance_id,
                run_id=new_run_id,
                entry={
                    "workers": workers,
                    "max_recoveries": max_recoveries,
                },
                observation=observe_run(workspace, new_run_id),
                plan={"action": "start_orchestrator", "reason": "post-recovery"},
            )
            return {
                "outcome": "recovered",
                "action": action,
                "recovery": recovery,
                "start": start_result,
            }
        if recovery.get("outcome") == "abandoned":
            queue.dead_letter(
                workspace.ai_team,
                f"recovery-{run_id}",
                error={
                    "code": "max_recoveries",
                    "message": recovery.get("reason"),
                },
                source={
                    "id": f"recovery-{run_id}",
                    "run_id": run_id,
                    "kind": "recovery",
                    "state": "dead_letter",
                },
            )
            registry.update_run_entry(
                workspace.ai_team,
                run_id,
                status="dead_letter",
                last_action=action,
                wait_reason="max_recoveries",
            )
            return {"outcome": "dead_letter", "action": action, "recovery": recovery}
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="needs_human",
            last_action=action,
            wait_reason=recovery.get("reason"),
        )
        return {"outcome": "needs_human", "action": action, "recovery": recovery}

    if action == "needs_human":
        registry.update_run_entry(
            workspace.ai_team,
            run_id,
            status="needs_human",
            last_action=action,
            wait_reason=plan.get("reason"),
        )
        journal.append_event(
            workspace.ai_team,
            instance_id=instance_id,
            event_type="needs_human",
            run_id=run_id,
            payload={"reason": plan.get("reason")},
        )
        return {"outcome": "needs_human", "action": action, "reason": plan.get("reason")}

    return {"outcome": "unknown_action", "action": action}


def reconcile_run(
    workspace: Workspace,
    *,
    instance_id: str,
    run_id: str,
    entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One idempotent reconcile cycle for a single supervised Run."""
    queue.reclaim_expired_leases(workspace.ai_team)
    # Drain journal (isolates corrupt events without blocking).
    journal.iter_events(workspace.ai_team, after_sequence=0)
    resolved_entry = entry or next(
        (item for item in registry.list_registered_runs(workspace.ai_team) if item["run_id"] == run_id),
        {"run_id": run_id, "workers": 1, "max_recoveries": 3},
    )
    observation = observe_run(workspace, run_id)
    plan = choose_action(observation, resolved_entry)
    result = execute_action(
        workspace,
        instance_id=instance_id,
        run_id=run_id,
        entry=resolved_entry,
        observation=observation,
        plan=plan,
    )
    return {
        "run_id": run_id,
        "observation": observation,
        "plan": plan,
        "result": result,
    }
