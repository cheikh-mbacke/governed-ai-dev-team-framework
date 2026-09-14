"""Managed orchestrator / agent process tracking for the supervisor."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.persistence.atomic import atomic_write_text
from governed_ai.core.supervisor.instance_lock import default_pid_is_alive
from governed_ai.core.supervisor.paths import ensure_supervisor_layout, process_dir
from governed_ai.core.supervisor.protocol import WorkerAttemptState
from governed_ai.core.supervisor.recovery import launch_orchestrator


class _ProcessHandle(Protocol):
    pid: int


LauncherFn = Callable[[Path, str, int], _ProcessHandle]


def _process_path(ai_team: Path, run_id: str) -> Path:
    return process_dir(ai_team) / f"{run_id}.json"


def read_process_record(ai_team: Path, run_id: str) -> dict[str, Any] | None:
    path = _process_path(ai_team, run_id)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def write_process_record(ai_team: Path, run_id: str, document: dict[str, Any]) -> None:
    ensure_supervisor_layout(ai_team)
    payload = dict(document)
    payload["run_id"] = run_id
    payload["updated_at"] = datetime.now(UTC).isoformat()
    atomic_write_text(_process_path(ai_team, run_id), json.dumps(payload, indent=2, sort_keys=True))


def start_orchestrator_process(
    workspace_root: Path,
    ai_team: Path,
    run_id: str,
    *,
    workers: int,
    lease_epoch: int,
    launcher: LauncherFn | None = None,
) -> dict[str, Any]:
    """Start a managed orchestrator. ``launcher`` is injectable for tests."""
    start = launcher or launch_orchestrator
    handle = start(workspace_root, run_id, workers)
    document = {
        "run_id": run_id,
        "pid": handle.pid,
        "status": WorkerAttemptState.STARTING.value,
        "worker_attempt_state": WorkerAttemptState.STARTING.value,
        "workers": workers,
        "lease_epoch": lease_epoch,
        "started_at": datetime.now(UTC).isoformat(),
        "heartbeat_at": datetime.now(UTC).isoformat(),
    }
    write_process_record(ai_team, run_id, document)
    return document


def mark_running(ai_team: Path, run_id: str) -> dict[str, Any] | None:
    document = read_process_record(ai_team, run_id)
    if document is None:
        return None
    document["status"] = WorkerAttemptState.RUNNING.value
    document["worker_attempt_state"] = WorkerAttemptState.RUNNING.value
    document["acknowledged_at"] = datetime.now(UTC).isoformat()
    document["heartbeat_at"] = datetime.now(UTC).isoformat()
    write_process_record(ai_team, run_id, document)
    return document


def process_is_alive(ai_team: Path, run_id: str) -> bool:
    document = read_process_record(ai_team, run_id)
    if document is None:
        return False
    return default_pid_is_alive(int(document.get("pid") or 0))


def terminate_process(
    ai_team: Path,
    run_id: str,
    *,
    grace_seconds: float = 2.0,
    expected_epoch: int | None = None,
) -> dict[str, Any]:
    """Bounded cancellation of a managed orchestrator process."""
    document = read_process_record(ai_team, run_id) or {"run_id": run_id}
    if expected_epoch is not None and int(document.get("lease_epoch") or 0) != expected_epoch:
        return {
            "outcome": "fencing_conflict",
            "run_id": run_id,
            "reason": "stale process epoch refused termination ownership",
        }
    pid = int(document.get("pid") or 0)
    if not pid or not default_pid_is_alive(pid):
        document["status"] = WorkerAttemptState.ORPHANED.value
        document["worker_attempt_state"] = WorkerAttemptState.ORPHANED.value
        write_process_record(ai_team, run_id, document)
        return {"outcome": "already_gone", "run_id": run_id, "pid": pid}

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                capture_output=True,
                check=False,
                timeout=max(1.0, grace_seconds),
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    deadline = time.monotonic() + max(0.1, grace_seconds)
    while time.monotonic() < deadline:
        if not default_pid_is_alive(pid):
            break
        time.sleep(0.05)

    if default_pid_is_alive(pid):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=2.0,
                )
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    alive = default_pid_is_alive(pid)
    document["status"] = (
        WorkerAttemptState.CANCELLED.value if not alive else WorkerAttemptState.RUNNING.value
    )
    document["worker_attempt_state"] = document["status"]
    document["terminated_at"] = datetime.now(UTC).isoformat()
    write_process_record(ai_team, run_id, document)
    return {
        "outcome": "cancelled" if not alive else "still_alive",
        "run_id": run_id,
        "pid": pid,
        "alive": alive,
    }


def legacy_orchestrator_process_alive(ai_team: Path, run_id: str) -> bool:
    """Compatibility with orchestrate.py process records under runs/processes/."""
    path = ai_team / "runs" / "processes" / f"{run_id}.json"
    if not path.is_file():
        return False
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return default_pid_is_alive(int(document.get("pid") or 0))
