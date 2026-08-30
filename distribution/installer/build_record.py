"""Build and persist Installation Record v2."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.installer.constants import SUPPORTED_UPDATE_FROM
from distribution.installer.ownership import (
    OWNER_CORE,
    OWNER_CURSOR,
    OWNER_DISTRIBUTION,
    UnclassifiableManagedFileError,
    partition_managed_files,
)
from distribution.installer.record import INSTALLATION_RECORD_FILE, LEGACY_VERSION_FILE, normalize_path

KNOWN_ADAPTER_IDS = frozenset({"cursor"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finalize_distribution_files(distribution_files: list[str]) -> list[str]:
    files = {normalize_path(path) for path in distribution_files}
    files.discard(normalize_path(LEGACY_VERSION_FILE))
    files.add(normalize_path(INSTALLATION_RECORD_FILE))
    return sorted(files)


def build_installation_record(
    *,
    project_id: str,
    version: str,
    managed_files: list[str],
    active_adapter_id: str = "cursor",
    installed_at: str,
    last_updated_at: str,
    migration_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    managed = [
        normalize_path(path)
        for path in managed_files
        if normalize_path(path)
        not in {
            normalize_path(LEGACY_VERSION_FILE),
            normalize_path(INSTALLATION_RECORD_FILE),
        }
    ]
    buckets = partition_managed_files(managed)
    if active_adapter_id not in KNOWN_ADAPTER_IDS:
        raise ValueError(f"unknown active_adapter_id: {active_adapter_id}")

    record: dict[str, Any] = {
        "schema_version": 2,
        "project_id": project_id,
        "active_adapter_id": active_adapter_id,
        "core": {
            "version": version,
            "managed_files": buckets[OWNER_CORE],
        },
        "adapters": [
            {
                "id": "cursor",
                "version": version,
                "managed_files": buckets[OWNER_CURSOR],
            }
        ],
        "distribution": {
            "version": version,
            "managed_files": _finalize_distribution_files(buckets[OWNER_DISTRIBUTION]),
        },
        "installed_at": installed_at,
        "last_updated_at": last_updated_at,
    }
    if migration_receipt is not None:
        record["migration_receipt"] = migration_receipt
    return record


def legacy_manifest_bytes(version: str, managed_files: list[str]) -> bytes:
    payload = {
        "schema_version": 1,
        "version": version,
        "managed_files": sorted(set(normalize_path(path) for path in managed_files)),
    }
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def write_installation_record(target: Path, record: dict[str, Any]) -> Path:
    path = target / INSTALLATION_RECORD_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_legacy_manifest(target: Path, version: str, managed_files: list[str]) -> Path:
    path = target / LEGACY_VERSION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(legacy_manifest_bytes(version, managed_files))
    return path


def finalize_installation_manifests(
    target: Path,
    *,
    project_id: str,
    version: str,
    managed_files: list[str],
    active_adapter_id: str = "cursor",
    installed_at: str | None = None,
    last_updated_at: str | None = None,
    existing_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write legacy v1 manifest then v2 record (v2 last). Returns the v2 record."""
    now = utc_now_iso()
    installed = installed_at or (existing_record or {}).get("installed_at") or now
    updated = last_updated_at or now
    record = build_installation_record(
        project_id=project_id,
        version=version,
        managed_files=managed_files,
        active_adapter_id=active_adapter_id,
        installed_at=installed,
        last_updated_at=updated,
        migration_receipt=(existing_record or {}).get("migration_receipt"),
    )
    union = sorted(
        set(managed_files)
        | set(record["core"]["managed_files"])
        | set(record["distribution"]["managed_files"])
        | set(record["adapters"][0]["managed_files"])
    )
    write_legacy_manifest(target, version, union)
    write_installation_record(target, record)
    return record


class InstallationValidationError(ValueError):
    """Pre-flight installation/update validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_installation_record(record: dict[str, Any]) -> None:
    adapter_id = str(record.get("active_adapter_id", ""))
    installed_ids = {
        str(entry.get("id", ""))
        for entry in record.get("adapters") or []
        if isinstance(entry, dict)
    }
    if adapter_id not in installed_ids:
        raise InstallationValidationError(
            "MISSING_ACTIVE_ADAPTER",
            f"active_adapter_id {adapter_id!r} has no installed adapter entry",
        )


def validate_update_path(installed_version: str | None, new_version: str) -> None:
    if installed_version not in SUPPORTED_UPDATE_FROM:
        raise InstallationValidationError(
            "UNSUPPORTED_VERSION_PATH",
            f"No safe migration path from {installed_version!r} to {new_version}",
        )