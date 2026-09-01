"""Build and persist Installation Record v2/v3."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.installer.ownership import (
    OWNER_CORE,
    OWNER_CURSOR,
    OWNER_DISTRIBUTION,
    partition_managed_files,
)
from distribution.installer.record import INSTALLATION_RECORD_FILE, LEGACY_VERSION_FILE, normalize_path
from distribution.installer.hashes import sha256_file

KNOWN_ADAPTER_IDS = frozenset({"cursor"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finalize_distribution_files(distribution_files: list[str]) -> list[str]:
    files = {normalize_path(path) for path in distribution_files}
    files.discard(normalize_path(LEGACY_VERSION_FILE))
    files.add(normalize_path(INSTALLATION_RECORD_FILE))
    return sorted(files)


def _hash_entries(paths: list[str], target: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in sorted(set(normalize_path(p) for p in paths)):
        file_path = target / path
        digest = sha256_file(file_path) if file_path.is_file() else "sha256:" + "0" * 64
        entries.append({"path": path, "installed_sha256": digest})
    return entries


def build_installation_record(
    *,
    project_id: str,
    version: str,
    managed_files: list[str],
    active_adapter_id: str = "cursor",
    installed_at: str,
    last_updated_at: str,
    target: Path | None = None,
    schema_version: int = 3,
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

    distribution_paths = _finalize_distribution_files(buckets[OWNER_DISTRIBUTION])

    if schema_version >= 3 and target is not None:
        core_files = _hash_entries(buckets[OWNER_CORE], target)
        cursor_files = _hash_entries(buckets[OWNER_CURSOR], target)
        distribution_files = _hash_entries(distribution_paths, target)
    else:
        core_files = buckets[OWNER_CORE]
        cursor_files = buckets[OWNER_CURSOR]
        distribution_files = distribution_paths

    record: dict[str, Any] = {
        "schema_version": schema_version,
        "project_id": project_id,
        "active_adapter_id": active_adapter_id,
        "core": {
            "version": version,
            "managed_files": core_files,
        },
        "adapters": [
            {
                "id": "cursor",
                "version": version,
                "managed_files": cursor_files,
            }
        ],
        "distribution": {
            "version": version,
            "managed_files": distribution_files,
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
    schema_version: int = 3,
) -> dict[str, Any]:
    """Write legacy v1 manifest then v2/v3 record (record last). Returns the record."""
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
        target=target,
        schema_version=schema_version,
        migration_receipt=(existing_record or {}).get("migration_receipt"),
    )
    union = sorted(managed_files_union_from_record(record))
    write_legacy_manifest(target, version, union)
    write_installation_record(target, record)
    return record


def managed_files_union_from_record(record: dict[str, Any]) -> set[str]:
    from distribution.installer.record import managed_files_union

    return managed_files_union(record)


from distribution.installer.errors import InstallationValidationError

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
