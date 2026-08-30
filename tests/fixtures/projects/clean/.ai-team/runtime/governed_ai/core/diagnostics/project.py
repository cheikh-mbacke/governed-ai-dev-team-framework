"""Core-side diagnostic queries shared by operator scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

COMMAND_FIELDS = (
    "setup",
    "build",
    "lint",
    "typecheck",
    "unit_test",
    "integration_test",
    "e2e_test",
)


def _load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def collect_open_human_events(project_root: Path) -> list[tuple[str, dict[str, Any]]]:
    """Return open events explicitly waiting on a human."""
    events_dir = project_root / ".ai-team" / "events"
    if not events_dir.is_dir():
        return []
    open_events: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(events_dir.glob("*.yaml")):
        event = _load_yaml(path)
        if not event:
            continue
        if event.get("status") == "open" and event.get("requires_human"):
            open_events.append((path.name, event))
    return open_events


def collect_in_flight_work_units(project_root: Path) -> list[tuple[str, str]]:
    """Return Work Units neither ready, done, cancelled nor unset."""
    wu_dir = project_root / ".ai-team" / "work-units"
    if not wu_dir.is_dir():
        return []
    in_flight: list[tuple[str, str]] = []
    for path in sorted(wu_dir.glob("*.yaml")):
        wu = _load_yaml(path)
        if not wu:
            continue
        status = wu.get("status")
        if status not in ("done", "cancelled", "ready", None):
            in_flight.append((path.stem, str(status)))
    return in_flight


def declared_profile_commands(project_root: Path) -> dict[str, str]:
    """Declared shell commands from project-profile.yaml."""
    profile = _load_yaml(project_root / ".ai-team" / "project-profile.yaml") or {}
    commands = profile.get("commands") if isinstance(profile.get("commands"), dict) else {}
    result: dict[str, str] = {}
    for field in COMMAND_FIELDS:
        value = commands.get(field)
        if isinstance(value, str) and value.strip():
            result[field] = value.strip()
    return result
