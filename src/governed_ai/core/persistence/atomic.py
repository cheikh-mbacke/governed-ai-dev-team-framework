"""Atomic file replacement on the same volume."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

_write_failure_hook: Callable[[Path], None] | None = None


def set_write_failure_hook(hook: Callable[[Path], None] | None) -> None:
    global _write_failure_hook
    _write_failure_hook = hook


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    if _write_failure_hook is not None:
        _write_failure_hook(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding=encoding)
    os.replace(temp_path, path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    if _write_failure_hook is not None:
        _write_failure_hook(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(content)
    os.replace(temp_path, path)
