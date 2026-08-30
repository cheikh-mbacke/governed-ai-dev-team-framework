"""Migrate installation-record.json schema v2 to v3 (content hashes)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.installer.record import (
    INSTALLATION_RECORD_FILE,
    is_v2_record,
    is_v3_record,
    load_installation_record,
    normalize_path,
)
from distribution.installer.hashes import sha256_file


class MigrationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MigrationResult:
    record: dict[str, Any]
    backup_path: Path | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _entries_from_section(entries: list[Any], target: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for entry in entries or []:
        if isinstance(entry, str):
            path = normalize_path(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            path = normalize_path(entry["path"])
        else:
            continue
        file_path = target / path
        digest = sha256_file(file_path) if file_path.is_file() else "sha256:" + "0" * 64
        result.append({"path": path, "installed_sha256": digest})
    return sorted(result, key=lambda item: item["path"])


def build_v3_record(v2_record: dict[str, Any], target: Path, *, migrated_at: str) -> dict[str, Any]:
    if not is_v2_record(v2_record):
        raise MigrationError("INVALID_V2_RECORD", "expected schema_version 2")

    record = json.loads(json.dumps(v2_record))
    record["schema_version"] = 3
    record["last_updated_at"] = migrated_at
    record["core"]["managed_files"] = _entries_from_section(
        v2_record.get("core", {}).get("managed_files"), target
    )
    record["distribution"]["managed_files"] = _entries_from_section(
        v2_record.get("distribution", {}).get("managed_files"), target
    )
    adapters = []
    for adapter in v2_record.get("adapters") or []:
        if not isinstance(adapter, dict):
            continue
        updated = dict(adapter)
        updated["managed_files"] = _entries_from_section(adapter.get("managed_files"), target)
        adapters.append(updated)
    record["adapters"] = adapters

    receipt = dict(record.get("migration_receipt") or {})
    receipt["v2_to_v3"] = {
        "migrated_at": migrated_at,
        "from_schema_version": 2,
    }
    record["migration_receipt"] = receipt
    return record


def migrate_v2_to_v3(
    target: Path,
    *,
    migrated_at: str | None = None,
    write_files: bool = True,
) -> MigrationResult:
    target = target.resolve()
    existing = load_installation_record(target)
    if existing is None:
        raise MigrationError("MISSING_RECORD", f"{INSTALLATION_RECORD_FILE.as_posix()} not found")
    if is_v3_record(existing):
        raise MigrationError("ALREADY_V3", "installation record is already schema_version 3")
    if not is_v2_record(existing):
        raise MigrationError("INVALID_RECORD", "expected v2 installation record")

    migrated_at_value = migrated_at or utc_now_iso()
    record = build_v3_record(existing, target, migrated_at=migrated_at_value)

    backup_path = None
    if write_files:
        backup_dir = target / ".ai-team" / "migration-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = migrated_at_value.replace(":", "").replace("+00:00", "Z")
        backup_path = backup_dir / f"installation-record-v2-{stamp}.json"
        backup_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        record_path = target / INSTALLATION_RECORD_FILE
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    return MigrationResult(record=record, backup_path=backup_path)


def ensure_installation_record_v3(
    target: Path,
    *,
    write_files: bool = True,
) -> MigrationResult | None:
    existing = load_installation_record(target)
    if existing is None or is_v3_record(existing):
        return None
    if is_v2_record(existing):
        return migrate_v2_to_v3(target, write_files=write_files)
    return None
