"""Supervisor daemon lifecycle: start, foreground loop, stop, reconcile-once."""

from __future__ import annotations

import json
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from governed_ai.core.persistence.atomic import atomic_write_text
from governed_ai.core.supervisor import journal, registry
from governed_ai.core.supervisor.instance_lock import (
    InstanceLock,
    InstanceLockError,
    acquire_instance_lock,
    read_instance_status,
)
from governed_ai.core.supervisor.paths import (
    ensure_supervisor_layout,
    heartbeat_path,
)
from governed_ai.core.supervisor.reconcile import reconcile_run
from governed_ai.core.workspace import Workspace

StopPredicate = Callable[[], bool]


@dataclass
class SupervisorDaemon:
    workspace: Workspace
    interval_seconds: float = 5.0
    heartbeat_stale_after_seconds: float = 120.0
    _lock: InstanceLock | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _accepting_work: bool = field(default=True, init=False, repr=False)

    @property
    def instance_id(self) -> str | None:
        return None if self._lock is None else self._lock.instance_id

    def acquire(self) -> InstanceLock:
        ensure_supervisor_layout(self.workspace.ai_team)
        self._lock = acquire_instance_lock(
            self.workspace.ai_team,
            heartbeat_stale_after_seconds=self.heartbeat_stale_after_seconds,
        )
        journal.append_event(
            self.workspace.ai_team,
            instance_id=self._lock.instance_id,
            event_type="daemon_started",
            payload={"pid": self._lock.pid},
        )
        self._write_heartbeat()
        return self._lock

    def _write_heartbeat(self) -> None:
        if self._lock is None:
            return
        document = self._lock.heartbeat()
        atomic_write_text(
            heartbeat_path(self.workspace.ai_team),
            json.dumps(
                {
                    "instance_id": self._lock.instance_id,
                    "pid": document.get("pid"),
                    "heartbeat_at": document.get("heartbeat_at"),
                    "accepting_work": self._accepting_work,
                    "uptime_started_at": self._lock.started_at,
                },
                indent=2,
                sort_keys=True,
            ),
        )

    def reconcile_once(self) -> list[dict[str, Any]]:
        if self._lock is None:
            raise InstanceLockError("daemon lock not acquired")
        if not self._accepting_work:
            return []
        results: list[dict[str, Any]] = []
        for entry in registry.list_registered_runs(self.workspace.ai_team):
            if self._stop.is_set():
                break
            results.append(
                reconcile_run(
                    self.workspace,
                    instance_id=self._lock.instance_id,
                    run_id=str(entry["run_id"]),
                    entry=entry,
                )
            )
        self._write_heartbeat()
        return results

    def run_forever(self, *, max_cycles: int | None = None) -> int:
        if self._lock is None:
            self.acquire()
        assert self._lock is not None
        self._install_signal_handlers()
        cycles = 0
        while not self._stop.is_set():
            try:
                self.reconcile_once()
            except Exception as exc:  # noqa: BLE001 — keep daemon alive; isolate per-cycle
                journal.append_event(
                    self.workspace.ai_team,
                    instance_id=self._lock.instance_id,
                    event_type="reconcile_error",
                    payload={"error": f"{type(exc).__name__}: {exc}"[:500]},
                )
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            self._stop.wait(max(0.1, self.interval_seconds))
        self.shutdown()
        return 0

    def request_stop(self) -> None:
        self._accepting_work = False
        self._stop.set()

    def shutdown(self) -> None:
        """Graceful stop: refuse new work, journal active processes, release lock.

        Managed orchestrator processes are left running so a successor daemon
        can reattach from durable process records. Attempts already ``started``
        are never silently forgotten — they appear in the shutdown journal.
        """
        self._accepting_work = False
        if self._lock is not None:
            active: list[dict[str, Any]] = []
            for entry in registry.list_registered_runs(self.workspace.ai_team):
                run_id = str(entry["run_id"])
                process = None
                try:
                    from governed_ai.core.supervisor.process import read_process_record

                    process = read_process_record(self.workspace.ai_team, run_id)
                except Exception:  # noqa: BLE001
                    process = None
                if process and process.get("worker_attempt_state") in {
                    "starting",
                    "running",
                    "leased",
                }:
                    active.append(
                        {
                            "run_id": run_id,
                            "pid": process.get("pid"),
                            "worker_attempt_state": process.get("worker_attempt_state"),
                            "lease_epoch": process.get("lease_epoch"),
                        }
                    )
            journal.append_event(
                self.workspace.ai_team,
                instance_id=self._lock.instance_id,
                event_type="daemon_stopping",
                payload={"active_attempts": active, "reattach_on_restart": True},
            )
            try:
                self._write_heartbeat()
            except Exception:  # noqa: BLE001
                pass
            self._lock.release()
            self._lock = None

    def run_governed_execution(self, **kwargs: Any) -> Any:
        """Compile + execute via the Gateway (production path; EXEC-GATEWAY-AC-16)."""
        from governed_ai.core.supervisor.execution_bridge import run_governed_execution

        if self._lock is None:
            raise InstanceLockError("daemon lock not acquired")
        kwargs.setdefault("instance_id", self._lock.instance_id)
        return run_governed_execution(self.workspace, **kwargs)

    def accept_execution(
        self,
        *,
        request: dict[str, Any],
        adapter: Any,
        work_unit: dict[str, Any],
        grant_allowed_paths: list[str],
        profile: dict[str, Any] | None = None,
        use_ephemeral_workspace: bool = True,
        run_independent_verification: bool = False,
    ) -> Any:
        """Accept an adapter result via the Agent Execution Gateway (EXEC-GATEWAY-AC-16)."""
        from governed_ai.core.supervisor.execution_bridge import accept_via_gateway

        if self._lock is None:
            raise InstanceLockError("daemon lock not acquired")
        return accept_via_gateway(
            self.workspace,
            request=request,
            adapter=adapter,
            work_unit=work_unit,
            grant_allowed_paths=grant_allowed_paths,
            profile=profile,
            instance_id=self._lock.instance_id,
            use_ephemeral_workspace=use_ephemeral_workspace,
            run_independent_verification=run_independent_verification,
        )

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: Any) -> None:
            journal.append_event(
                self.workspace.ai_team,
                instance_id=self.instance_id or "unknown",
                event_type="signal_received",
                payload={"signum": signum},
            )
            self.request_stop()

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Not in main thread — CLI wrapper handles KeyboardInterrupt.
                pass


def register_run(
    workspace: Workspace,
    run_id: str,
    *,
    workers: int = 1,
    max_recoveries: int = 3,
) -> dict[str, Any]:
    return registry.register_run(
        workspace.ai_team,
        run_id,
        workers=workers,
        max_recoveries=max_recoveries,
    )


def unregister_run(workspace: Workspace, run_id: str) -> bool:
    return registry.unregister_run(workspace.ai_team, run_id)


def daemon_status_payload(workspace: Workspace) -> dict[str, Any]:
    from governed_ai.core.supervisor.status import build_status

    return build_status(workspace)


def spawn_background(workspace: Workspace, *, interval_seconds: float = 5.0) -> dict[str, Any]:
    """Start daemon in a detached process (used by ``daemon start``)."""
    import os
    import subprocess
    import sys

    command = [
        sys.executable,
        str(workspace.root / "scripts" / "ai-team" / "daemon.py"),
        "run",
        "--foreground",
        "--interval-seconds",
        str(interval_seconds),
    ]
    environment = dict(os.environ)
    kwargs: dict[str, Any] = {
        "cwd": str(workspace.root),
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
    handle = subprocess.Popen(command, **kwargs)
    # Brief settle so the child can acquire the lock before status.
    time.sleep(0.2)
    status = read_instance_status(workspace.ai_team)
    return {"spawned_pid": handle.pid, "instance": status}
