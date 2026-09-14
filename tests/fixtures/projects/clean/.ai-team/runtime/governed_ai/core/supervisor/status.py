"""Human and JSON status / doctor views for the supervisor daemon."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.supervisor import journal, queue, registry
from governed_ai.core.supervisor.instance_lock import read_instance_status
from governed_ai.core.supervisor.paths import heartbeat_path, supervisor_root
from governed_ai.core.supervisor.reconcile import observe_run
from governed_ai.core.workspace import Workspace


def _uptime_seconds(started_at: str | None) -> float | None:
    if not started_at:
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
    except ValueError:
        return None
    return max(0.0, (datetime.now(UTC) - started).total_seconds())


def _read_heartbeat(ai_team: Path) -> dict[str, Any]:
    path = heartbeat_path(ai_team)
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def build_status(workspace: Workspace) -> dict[str, Any]:
    ai_team = workspace.ai_team
    instance = read_instance_status(ai_team)
    heartbeat = _read_heartbeat(ai_team)
    runs: list[dict[str, Any]] = []
    for entry in registry.list_registered_runs(ai_team):
        observation = observe_run(workspace, str(entry["run_id"]))
        progress = observation.get("progress") or {}
        runs.append(
            {
                "run_id": entry["run_id"],
                "registry_status": entry.get("status"),
                "run_status": observation.get("run_status"),
                "progress_state": progress.get("state"),
                "last_progress_at": progress.get("last_progress_at"),
                "minutes_without_progress": progress.get("minutes_without_progress"),
                "process_alive": observation.get("process_alive"),
                "active_pid": (observation.get("process") or {}).get("pid")
                or entry.get("active_pid"),
                "current_lease": observation.get("current_lease"),
                "recovery_count": observation.get("recovery_count")
                or entry.get("recovery_count"),
                "next_action": entry.get("next_action"),
                "wait_reason": entry.get("wait_reason"),
                "last_action": entry.get("last_action"),
                "is_progressing": progress.get("state") in {"working", "progressing"},
            }
        )
    queue_items = queue.list_items(ai_team, include_dead_letter=True)
    dead_letters = [item for item in queue_items if item.get("state") == "dead_letter"]
    active_workers = [
        item
        for item in queue_items
        if item.get("state") in {"leased", "acknowledged"}
        or item.get("worker_attempt_state") in {"starting", "running"}
    ]
    alerts = journal.load_alerts(ai_team)
    started_at = (instance.get("instance") or {}).get("started_at") or heartbeat.get(
        "uptime_started_at"
    )
    progressing = any(item.get("is_progressing") for item in runs)
    return {
        "schema_version": 1,
        "daemon": {
            "state": instance.get("state"),
            "lock_present": instance.get("lock_present"),
            "orphan": instance.get("orphan"),
            "orphan_reason": instance.get("orphan_reason"),
            "instance_id": (instance.get("instance") or {}).get("instance_id"),
            "pid": (instance.get("instance") or {}).get("pid"),
            "pid_alive": instance.get("pid_alive"),
            "heartbeat_at": heartbeat.get("heartbeat_at")
            or (instance.get("instance") or {}).get("heartbeat_at"),
            "started_at": started_at,
            "uptime_seconds": _uptime_seconds(started_at),
            "accepting_work": heartbeat.get("accepting_work"),
            "supervisor_root": str(supervisor_root(ai_team)),
        },
        "progressing": progressing,
        "runs": runs,
        "workers_active": active_workers,
        "dead_letter": dead_letters,
        "alerts": alerts,
        "queue_depth": len([item for item in queue_items if item.get("state") == "queued"]),
        "observed_at": datetime.now(UTC).isoformat(),
    }


def build_doctor(workspace: Workspace) -> dict[str, Any]:
    status = build_status(workspace)
    findings: list[dict[str, str]] = []
    daemon = status["daemon"]
    if daemon.get("state") == "orphan_lock":
        findings.append(
            {
                "severity": "high",
                "code": "orphan_lock",
                "message": "supervisor lock present but owner process is gone",
            }
        )
    if daemon.get("state") == "stopped":
        findings.append(
            {
                "severity": "medium",
                "code": "daemon_stopped",
                "message": "no supervisor daemon is running",
            }
        )
    for run in status["runs"]:
        if run.get("progress_state") == "stalled_no_progress":
            findings.append(
                {
                    "severity": "high",
                    "code": "stalled_no_progress",
                    "message": f"run {run['run_id']} has no useful progress",
                }
            )
        if run.get("registry_status") == "needs_human":
            findings.append(
                {
                    "severity": "high",
                    "code": "needs_human",
                    "message": f"run {run['run_id']} requires human intervention",
                }
            )
        if run.get("registry_status") == "dead_letter":
            findings.append(
                {
                    "severity": "high",
                    "code": "dead_letter",
                    "message": f"run {run['run_id']} exhausted recovery",
                }
            )
    for alert in status.get("alerts") or []:
        findings.append(
            {
                "severity": "high",
                "code": str(alert.get("code") or "alert"),
                "message": str(alert.get("error") or alert),
            }
        )
    if status.get("dead_letter"):
        findings.append(
            {
                "severity": "medium",
                "code": "dead_letter_queue",
                "message": f"{len(status['dead_letter'])} dead-letter item(s)",
            }
        )
    status["doctor"] = {
        "ok": not any(item["severity"] == "high" for item in findings),
        "findings": findings,
    }
    return status


def format_status_text(payload: dict[str, Any]) -> str:
    daemon = payload.get("daemon") or {}
    lines = [
        f"Daemon: {daemon.get('state')} instance={daemon.get('instance_id')} "
        f"pid={daemon.get('pid')} heartbeat={daemon.get('heartbeat_at')}",
        f"Uptime seconds: {daemon.get('uptime_seconds')}",
        f"Progressing: {payload.get('progressing')}",
        f"Queue depth: {payload.get('queue_depth')} "
        f"dead-letter: {len(payload.get('dead_letter') or [])}",
        f"Supervised runs: {len(payload.get('runs') or [])}",
    ]
    for run in payload.get("runs") or []:
        lines.append(
            f"  - {run.get('run_id')}: run={run.get('run_status')} "
            f"progress={run.get('progress_state')} "
            f"alive={run.get('process_alive')} "
            f"next={run.get('next_action')} wait={run.get('wait_reason')}"
        )
    doctor = payload.get("doctor")
    if doctor is not None:
        lines.append(f"Doctor ok: {doctor.get('ok')}")
        for finding in doctor.get("findings") or []:
            lines.append(f"  ! [{finding.get('severity')}] {finding.get('code')}: {finding.get('message')}")
    return "\n".join(lines)
