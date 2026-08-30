"""Atomic file replacement on the same volume."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path

_write_failure_hook: Callable[[Path], None] | None = None

# Windows enforces mandatory file-sharing locks that POSIX does not: if another
# thread has `path` open for reading (even briefly, e.g. mid-`read_text()`)
# exactly when this replaces it, `os.replace()` raises PermissionError
# (WinError 5) instead of the atomic swap POSIX guarantees unconditionally.
# Retrying briefly is the standard mitigation — surfaced by real concurrent
# orchestrator ticks (Document 6 §11), not something a single-threaded caller
# would ever hit.
_REPLACE_RETRY_ATTEMPTS = 200
_REPLACE_RETRY_DELAY_SECONDS = 0.02


def set_write_failure_hook(hook: Callable[[Path], None] | None) -> None:
    global _write_failure_hook
    _write_failure_hook = hook


def _replace_with_retry(temp_path: Path, path: Path) -> None:
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    if _write_failure_hook is not None:
        _write_failure_hook(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(content, encoding=encoding)
        _replace_with_retry(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    if _write_failure_hook is not None:
        _write_failure_hook(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(content)
        _replace_with_retry(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
