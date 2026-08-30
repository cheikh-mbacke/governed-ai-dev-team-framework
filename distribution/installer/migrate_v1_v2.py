"""Migrate legacy framework-version.json (v1) to installation-record.json (v2)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.installer.ownership import (
    OWNER_CORE,
    OWNER_CURSOR,
    OWNER_DISTRIBUTION,
    UnclassifiableManagedFileError,
    partition_managed_files,
)
from distribution.installer.profile import (
    AdapterVersionMismatchError,
    UnknownActiveAdapterError,
    load_project_profile,
    resolve_active_adapter_id,
    write_project_profile,
)
from distribution.installer.record import (
    INSTALLATION_RECORD_FILE,
    LEGACY_VERSION_FILE,
    is_v1_manifest,
    load_installation_record,
    load_legacy_manifest,
    managed_files_union,
    normalize_path,
)

MIGRATION_BACKUPS_DIR = Path(".ai-team/migration-backups")


class MigrationError(Exception):
    """Base class for installation record migration failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MigrationResult:
    record: dict[str, Any]
    backup_path: Path
    profile_updated: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def backup_stamp(iso_timestamp: str) -> str:
    return iso_timestamp.replace(":", "").replace("+00:00", "Z")


def _finalize_distribution_files(distribution_files: list[str]) -> list[str]:
    files = {normalize_path(path) for path in distribution_files}
    files.discard(normalize_path(LEGACY_VERSION_FILE))
    files.add(normalize_path(INSTALLATION_RECORD_FILE))
    return sorted(files)


def build_v2_record(
    v1_manifest: dict[str, Any],
    *,
    project_id: str,
    active_adapter_id: str,
    migrated_at: str,
    installed_at: str | None = None,
    target_version: str | None = None,
    backup_path: str | None = None,
) -> dict[str, Any]:
    legacy_version = str(v1_manifest["version"])
    version = target_version or legacy_version
    managed = [
        normalize_path(path)
        for path in v1_manifest.get("managed_files") or []
        if normalize_path(path) != normalize_path(LEGACY_VERSION_FILE)
    ]

    try:
        buckets = partition_managed_files(managed)
    except UnclassifiableManagedFileError as exc:
        raise MigrationError("UNCLASSIFIABLE_MANAGED_FILE", str(exc)) from exc

    distribution_files = _finalize_distribution_files(buckets[OWNER_DISTRIBUTION])

    adapters = [
        {
            "id": "cursor",
            "version": version,
            "managed_files": buckets[OWNER_CURSOR],
        }
    ]
    if active_adapter_id not in {entry["id"] for entry in adapters}:
        raise MigrationError(
            "UNKNOWN_ACTIVE_ADAPTER",
            f"active_adapter_id {active_adapter_id!r} is not installed",
        )

    installed_at_value = installed_at or migrated_at
    receipt: dict[str, Any] = {
        "from_schema_version": 1,
        "from_manifest_path": LEGACY_VERSION_FILE.as_posix(),
        "legacy_version": legacy_version,
        "migrated_at": migrated_at,
    }
    if backup_path:
        receipt["backup_path"] = backup_path
    if installed_at is None:
        receipt["installed_at_provenance"] = "derived_at_migration"

    return {
        "schema_version": 2,
        "project_id": project_id,
        "active_adapter_id": active_adapter_id,
        "core": {
            "version": version,
            "managed_files": buckets[OWNER_CORE],
        },
        "adapters": adapters,
        "distribution": {
            "version": version,
            "managed_files": distribution_files,
        },
        "installed_at": installed_at_value,
        "last_updated_at": migrated_at,
        "migration_receipt": receipt,
    }


def validate_v2_preserve_v1_managed(v1_manifest: dict[str, Any], record: dict[str, Any]) -> None:
    original = {
        normalize_path(path)
        for path in v1_manifest.get("managed_files") or []
        if normalize_path(path) != normalize_path(LEGACY_VERSION_FILE)
    }
    migrated = managed_files_union(record)
    migrated.discard(normalize_path(INSTALLATION_RECORD_FILE))
    if original != migrated:
        missing = sorted(original - migrated)
        extra = sorted(migrated - original)
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected: {', '.join(extra)}")
        raise MigrationError(
            "MANAGED_FILES_DRIFT",
            "v2 record does not preserve v1 managed_files — " + "; ".join(details),
        )


def backup_legacy_manifest(target: Path, *, migrated_at: str) -> Path:
    source = target / LEGACY_VERSION_FILE
    backup_dir = target / MIGRATION_BACKUPS_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"framework-version-{backup_stamp(migrated_at)}.json"
    shutil.copy2(source, backup_path)
    return backup_path


def migrate_v1_to_v2(
    target: Path,
    *,
    project_id: str | None = None,
    migrated_at: str | None = None,
    target_version: str | None = None,
    write_files: bool = True,
) -> MigrationResult:
    """Migrate ``framework-version.json`` v1 to ``installation-record.json`` v2."""
    target = target.resolve()
    existing = load_installation_record(target)
    if existing is not None:
        raise MigrationError(
            "ALREADY_MIGRATED",
            f"{INSTALLATION_RECORD_FILE.as_posix()} already exists",
        )

    v1_manifest = load_legacy_manifest(target)
    if not is_v1_manifest(v1_manifest):
        raise MigrationError("INVALID_V1_MANIFEST", "legacy manifest is not schema_version 1")

    profile = load_project_profile(target)
    resolved_project_id = project_id or str(profile.get("project", {}).get("id", ""))
    if not resolved_project_id:
        raise MigrationError("MISSING_PROJECT_ID", "project_id required for migration")

    legacy_version = str(v1_manifest["version"])
    version = target_version or legacy_version
    migrated_at_value = migrated_at or utc_now_iso()

    try:
        active_adapter_id, updated_profile, profile_mutated = resolve_active_adapter_id(
            profile,
            cursor_version=version,
        )
    except UnknownActiveAdapterError as exc:
        raise MigrationError("UNKNOWN_ACTIVE_ADAPTER", str(exc)) from exc
    except AdapterVersionMismatchError as exc:
        raise MigrationError("ADAPTER_VERSION_MISMATCH", str(exc)) from exc

    backup_path = backup_legacy_manifest(target, migrated_at=migrated_at_value)
    record = build_v2_record(
        v1_manifest,
        project_id=resolved_project_id,
        active_adapter_id=active_adapter_id,
        migrated_at=migrated_at_value,
        target_version=target_version,
        backup_path=backup_path.relative_to(target).as_posix(),
    )
    record["migration_receipt"]["backup_path"] = backup_path.relative_to(target).as_posix()
    validate_v2_preserve_v1_managed(v1_manifest, record)

    if write_files:
        record_path = target / INSTALLATION_RECORD_FILE
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if profile_mutated:
            write_project_profile(target, updated_profile)

    return MigrationResult(
        record=record,
        backup_path=backup_path,
        profile_updated=profile_mutated,
    )


def ensure_installation_record_v2(
    target: Path,
    *,
    target_version: str | None = None,
    write_files: bool = True,
) -> MigrationResult | None:
    """Migrate legacy v1 manifest when v2 record is absent."""
    if load_installation_record(target) is not None:
        return None
    legacy_path = target / LEGACY_VERSION_FILE
    if not legacy_path.is_file():
        return None
    return migrate_v1_to_v2(target, target_version=target_version, write_files=write_files)
