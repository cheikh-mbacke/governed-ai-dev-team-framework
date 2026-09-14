"""Filesystem layout for supervisor operational state."""

from __future__ import annotations

from pathlib import Path

SUPERVISOR_DIRNAME = "supervisor"


def supervisor_root(ai_team: Path) -> Path:
    return ai_team / SUPERVISOR_DIRNAME


def instance_lock_path(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "instance.lock.json"


def heartbeat_path(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "heartbeat.json"


def registry_path(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "registry.json"


def queue_dir(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "queue"


def dead_letter_dir(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "dead-letter"


def journal_dir(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "journal"


def process_dir(ai_team: Path) -> Path:
    return supervisor_root(ai_team) / "processes"


def ensure_supervisor_layout(ai_team: Path) -> Path:
    root = supervisor_root(ai_team)
    for path in (
        root,
        queue_dir(ai_team),
        dead_letter_dir(ai_team),
        journal_dir(ai_team),
        process_dir(ai_team),
    ):
        path.mkdir(parents=True, exist_ok=True)
    return root
