"""Project profile helpers for installation migration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from distribution.installer.record import KNOWN_ADAPTER_IDS


def _yaml():
    import yaml

    return yaml


class UnknownActiveAdapterError(ValueError):
    """Profile declares an adapter that is not installed."""


class AdapterVersionMismatchError(ValueError):
    """Legacy adapter version does not match migrated adapter entry."""


def load_project_profile(target: Path) -> dict[str, Any]:
    path = target / ".ai-team" / "project-profile.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"missing project profile: {path}")
    data = _yaml().safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("project-profile.yaml root must be a mapping")
    return data


def write_project_profile(target: Path, profile: dict[str, Any]) -> None:
    path = target / ".ai-team" / "project-profile.yaml"
    path.write_text(
        _yaml().safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def resolve_active_adapter_id(
    profile: dict[str, Any],
    *,
    cursor_version: str,
) -> tuple[str, dict[str, Any], bool]:
    """Return active adapter id, possibly updated profile, and whether profile was mutated."""
    updated = dict(profile)
    mutated = False

    if "active_adapter_id" in updated:
        adapter_id = str(updated["active_adapter_id"])
        if adapter_id not in KNOWN_ADAPTER_IDS:
            raise UnknownActiveAdapterError(
                f"unknown active_adapter_id: {adapter_id!r}"
            )
        return adapter_id, updated, mutated

    legacy_adapter = updated.get("adapter")
    if isinstance(legacy_adapter, dict):
        adapter_id = str(legacy_adapter.get("id", ""))
        legacy_version = str(legacy_adapter.get("version", ""))
        if adapter_id not in KNOWN_ADAPTER_IDS:
            raise UnknownActiveAdapterError(
                f"unknown legacy adapter id: {adapter_id!r}"
            )
        if legacy_version and legacy_version != cursor_version:
            raise AdapterVersionMismatchError(
                f"legacy adapter version {legacy_version!r} != migrated cursor {cursor_version!r}"
            )
        updated["active_adapter_id"] = adapter_id
        mutated = True
        return adapter_id, updated, mutated

    updated["active_adapter_id"] = "cursor"
    mutated = True
    return "cursor", updated, mutated
