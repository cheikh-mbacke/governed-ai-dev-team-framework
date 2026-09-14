"""Single-instance supervisor lock with orphan recovery."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.persistence.atomic import atomic_write_text
from governed_ai.core.supervisor.paths import ensure_supervisor_layout, instance_lock_path

PidAliveFn = Callable[[int], bool]
ProcessStartFn = Callable[[int], float | None]


class InstanceLockError(RuntimeError):
    """Raised when another live supervisor already owns the workspace."""


def default_pid_is_alive(pid: int) -> bool:
    """Return whether ``pid`` appears to be a live OS process.

    On Windows, ``os.kill(pid, 0)`` is **not** a liveness probe: signal ``0`` is
    ``CTRL_C_EVENT`` and would interrupt the current console. Use OpenProcess.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # PROCESS_QUERY_LIMITED_INFORMATION — enough to prove the handle opens.
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            int(pid),
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we cannot signal it — treat as alive.
        return True
    except OSError:
        return False
    return True


def default_process_start_time(pid: int) -> float | None:
    """Best-effort process start time (seconds since epoch).

    Linux: ``/proc/<pid>/stat`` field 22 (starttime) converted via btime.
    Windows / others: ``None`` — lock recovery then relies on PID death and
    heartbeat staleness only (never reclaim a fresh heartbeat).
    """
    if os.name != "posix":
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # comm may contain spaces/parentheses; split after last ')'
        after_comm = stat.rsplit(")", 1)[1].strip().split()
        start_ticks = int(after_comm[19])
        ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
        btime_line = next(
            line
            for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines()
            if line.startswith("btime ")
        )
        btime = int(btime_line.split()[1])
        return btime + (start_ticks / float(ticks))
    except (OSError, ValueError, IndexError, StopIteration, KeyError, AttributeError):
        return None


@dataclass(slots=True)
class InstanceLock:
    path: Path
    instance_id: str
    pid: int
    started_at: str
    workspace_id: str
    token: str

    def heartbeat(self, *, now: datetime | None = None) -> dict[str, Any]:
        observed = now or datetime.now(UTC)
        document = self.read()
        if document.get("token") != self.token:
            raise InstanceLockError("instance lock token mismatch during heartbeat")
        document["heartbeat_at"] = observed.isoformat()
        document["pid"] = os.getpid()
        atomic_write_text(self.path, json.dumps(document, indent=2, sort_keys=True))
        return document

    def read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def release(self) -> None:
        if not self.path.is_file():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if document.get("token") != self.token:
            return
        self.path.unlink(missing_ok=True)


def _workspace_id(ai_team: Path) -> str:
    return str(ai_team.resolve())


def _read_lock(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def _is_orphan(
    document: dict[str, Any],
    *,
    pid_is_alive: PidAliveFn,
    process_start_time: ProcessStartFn,
    heartbeat_stale_after_seconds: float,
    now: datetime,
) -> tuple[bool, str]:
    pid = int(document.get("pid") or 0)
    if not pid_is_alive(pid):
        return True, "pid_not_alive"

    heartbeat_raw = document.get("heartbeat_at") or document.get("started_at")
    try:
        heartbeat = datetime.fromisoformat(str(heartbeat_raw).replace("Z", "+00:00"))
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
    except ValueError:
        return True, "invalid_heartbeat"

    age = (now - heartbeat).total_seconds()
    start_time = process_start_time(pid)
    lock_started_raw = document.get("started_at")
    if start_time is not None and lock_started_raw:
        try:
            lock_started = datetime.fromisoformat(str(lock_started_raw).replace("Z", "+00:00"))
            if lock_started.tzinfo is None:
                lock_started = lock_started.replace(tzinfo=UTC)
            # PID reused by a newer process after the lock owner died uncleanly.
            if start_time > lock_started.timestamp() + 1.0:
                return True, "pid_reused"
        except ValueError:
            return True, "invalid_started_at"

    if age > heartbeat_stale_after_seconds and start_time is None:
        # Without OS start-time evidence, never reclaim a live PID — only report.
        return False, "live_pid_stale_heartbeat"
    return False, "live"


def acquire_instance_lock(
    ai_team: Path,
    *,
    heartbeat_stale_after_seconds: float = 120.0,
    pid_is_alive: PidAliveFn | None = None,
    process_start_time: ProcessStartFn | None = None,
    now: datetime | None = None,
) -> InstanceLock:
    """Acquire the unique supervisor lock for ``ai_team``.

    Never deletes a lock belonging to a process that is still alive with a
    plausible identity. Orphan recovery is limited to dead PIDs and proven
    PID-reuse cases.
    """
    ensure_supervisor_layout(ai_team)
    path = instance_lock_path(ai_team)
    alive = pid_is_alive or default_pid_is_alive
    start_time_fn = process_start_time or default_process_start_time
    observed = now or datetime.now(UTC)
    workspace = _workspace_id(ai_team)

    existing = _read_lock(path)
    reclaimed_reason: str | None = None
    if existing is not None:
        orphan, reason = _is_orphan(
            existing,
            pid_is_alive=alive,
            process_start_time=start_time_fn,
            heartbeat_stale_after_seconds=heartbeat_stale_after_seconds,
            now=observed,
        )
        if not orphan:
            raise InstanceLockError(
                f"supervisor already active "
                f"(instance_id={existing.get('instance_id')} pid={existing.get('pid')} "
                f"reason={reason})"
            )
        reclaimed_reason = reason
        # Remove only after confirming the lock is orphaned.
        try:
            path.unlink()
        except OSError as exc:
            raise InstanceLockError(f"could not reclaim orphan lock: {exc}") from exc

    instance_id = str(uuid.uuid4())
    token = uuid.uuid4().hex
    started_at = observed.isoformat()
    document = {
        "schema_version": 1,
        "instance_id": instance_id,
        "token": token,
        "pid": os.getpid(),
        "started_at": started_at,
        "heartbeat_at": started_at,
        "workspace_id": workspace,
        "reclaimed_reason": reclaimed_reason,
    }
    # Atomic exclusive create — concurrent starters cannot both succeed.
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
    except FileExistsError as exc:
        raise InstanceLockError("concurrent supervisor start lost the lock race") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(document, indent=2, sort_keys=True))
        handle.flush()
        os.fsync(handle.fileno())
    return InstanceLock(
        path=path,
        instance_id=instance_id,
        pid=os.getpid(),
        started_at=started_at,
        workspace_id=workspace,
        token=token,
    )


def read_instance_status(
    ai_team: Path,
    *,
    pid_is_alive: PidAliveFn | None = None,
    process_start_time: ProcessStartFn | None = None,
    heartbeat_stale_after_seconds: float = 120.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = instance_lock_path(ai_team)
    document = _read_lock(path)
    if document is None:
        return {"state": "stopped", "lock_present": False}
    alive = pid_is_alive or default_pid_is_alive
    start_time_fn = process_start_time or default_process_start_time
    observed = now or datetime.now(UTC)
    orphan, reason = _is_orphan(
        document,
        pid_is_alive=alive,
        process_start_time=start_time_fn,
        heartbeat_stale_after_seconds=heartbeat_stale_after_seconds,
        now=observed,
    )
    return {
        "state": "orphan_lock" if orphan else "running",
        "lock_present": True,
        "orphan": orphan,
        "orphan_reason": reason if orphan else None,
        "instance": document,
        "pid_alive": alive(int(document.get("pid") or 0)),
    }


def wait_briefly(seconds: float = 0.05) -> None:
    time.sleep(seconds)
