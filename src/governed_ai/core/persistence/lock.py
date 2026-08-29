"""Exclusive project lock under .ai-team/locks/."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from governed_ai.core.commands.errors import ErrorCode, GatewayError


@dataclass(slots=True)
class ProjectLock:
    path: Path
    token: str

    def release(self) -> None:
        if self.path.is_file():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if payload.get("token") == self.token:
                self.path.unlink(missing_ok=True)


def acquire_project_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = 30.0,
    poll_interval: float = 0.05,
) -> ProjectLock:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = str(uuid.uuid4())
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise GatewayError(
                    ErrorCode.CONFLICT,
                    "project lock already held",
                    "/lock",
                ) from None
            time.sleep(poll_interval)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "token": token,
                        "pid": os.getpid(),
                        "acquired_at": datetime.now(UTC).isoformat(),
                    }
                )
            )
        return ProjectLock(path=lock_path, token=token)


def force_release_stale_lock(lock_path: Path, *, max_age_seconds: float = 3600) -> None:
    """Test helper — remove lock files older than max_age."""
    if not lock_path.is_file():
        return
    age = time.time() - lock_path.stat().st_mtime
    if age > max_age_seconds:
        lock_path.unlink(missing_ok=True)
