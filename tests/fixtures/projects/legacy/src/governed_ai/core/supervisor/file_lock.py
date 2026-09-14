"""Cross-process file lock for supervisor queue/journal mutations."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class SupervisorLockError(RuntimeError):
    """Raised when a supervisor file lock cannot be acquired."""


@contextmanager
def exclusive_file_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = 10.0,
    poll_seconds: float = 0.01,
) -> Iterator[None]:
    """Exclusive lock via O_EXCL lockfile with stale recovery.

    Writers that die mid-section may leave a lockfile; after ``timeout_seconds``
    a waiter may reclaim a lock whose mtime is older than the timeout.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
            break
        except (FileExistsError, PermissionError):
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > timeout_seconds:
                try:
                    lock_path.unlink()
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                raise SupervisorLockError(f"timed out waiting for lock {lock_path}")
            time.sleep(poll_seconds)
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        for _ in range(50):
            try:
                lock_path.unlink(missing_ok=True)
                break
            except OSError:
                time.sleep(0.02)
