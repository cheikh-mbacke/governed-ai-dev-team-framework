"""Deterministic v1→v2 migration for mutable governance aggregates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

MIGRATION_ID = "mutable-schema-v2"
V2_FIELDS = frozenset({"revision", "created_at", "updated_at"})
GATE_DECISION_REQUIRED = ("id", "gate", "status", "by", "at")
VALID_GATES = frozenset({"G0", "G1", "G2", "G3", "G4"})

MUTABLE_DIRECTORIES: tuple[tuple[str, str], ...] = (
    ("work-units", "work-unit.schema.json"),
    ("decisions", "decision.schema.json"),
    ("findings", "finding.schema.json"),
    ("acceptance", "acceptance.schema.json"),
    ("release-candidates", "release-candidate.schema.json"),
)


class MigrationFailure(Exception):
    """Raised when migration cannot proceed without inventing business data."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass
class TimestampProvenance:
    field: str
    value: str
    source: str


@dataclass
class MutableV2Change:
    path: Path
    original_bytes: bytes
    migrated_bytes: bytes
    provenance: list[TimestampProvenance] = field(default_factory=list)


@dataclass
class MutableV2Plan:
    changes: list[MutableV2Change]
    skipped: list[Path] = field(default_factory=list)


def _is_gate_decision_document(document: dict[str, Any]) -> bool:
    if document.get("type") == "GATE_DECISION_REQUEST":
        return False
    if not all(field in document for field in GATE_DECISION_REQUIRED):
        return False
    return document.get("gate") in VALID_GATES


def _load_schema(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: schema must be an object")
    return data


def _business_required_fields(schema: dict[str, Any]) -> list[str]:
    return [name for name in schema.get("required", []) if name not in V2_FIELDS]


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _needs_v2_migration(document: dict[str, Any]) -> bool:
    revision = document.get("revision")
    created_at = document.get("created_at")
    updated_at = document.get("updated_at")
    if isinstance(revision, int) and revision >= 1 and created_at and updated_at:
        return False
    return True


def _migrate_document(
    document: dict[str, Any],
    *,
    schema: dict[str, Any],
    migrated_at: str,
) -> tuple[dict[str, Any], list[TimestampProvenance]]:
    for field_name in _business_required_fields(schema):
        if not _is_present(document.get(field_name)):
            raise MigrationFailure(
                Path("."),
                f"missing required business field {field_name!r}",
            )

    migrated = dict(document)
    provenance: list[TimestampProvenance] = []

    revision = migrated.get("revision")
    if revision is None:
        migrated["revision"] = 1
    elif not isinstance(revision, int):
        raise MigrationFailure(Path("."), "revision must be integer when present")

    for timestamp_field in ("created_at", "updated_at"):
        if _is_present(migrated.get(timestamp_field)):
            continue
        migrated[timestamp_field] = migrated_at
        provenance.append(
            TimestampProvenance(
                field=timestamp_field,
                value=migrated_at,
                source=f"migration:{MIGRATION_ID}",
            )
        )

    return migrated, provenance


def _iter_yaml_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files: list[Path] = []
    for pattern in ("*.yaml", "*.yml"):
        files.extend(directory.glob(pattern))
    return sorted(files)


def plan_mutable_v2(target: Path, *, migrated_at: str | None = None) -> MutableV2Plan:
    ai_team = target / ".ai-team"
    schemas_dir = ai_team / "schemas"
    if not schemas_dir.is_dir():
        return MutableV2Plan(changes=[], skipped=[])
    timestamp = migrated_at or datetime.now(UTC).isoformat()
    changes: list[MutableV2Change] = []
    skipped: list[Path] = []

    for relative_dir, schema_name in MUTABLE_DIRECTORIES:
        schema = _load_schema(schemas_dir / schema_name)
        directory = ai_team / relative_dir
        for path in _iter_yaml_files(directory):
            original = path.read_bytes()
            document = yaml.safe_load(original.decode("utf-8"))
            if not isinstance(document, dict):
                raise MigrationFailure(path, "document must be a mapping")

            if relative_dir == "decisions" and _is_gate_decision_document(document):
                skipped.append(path)
                continue

            if not _needs_v2_migration(document):
                continue

            try:
                migrated_document, provenance = _migrate_document(
                    document,
                    schema=schema,
                    migrated_at=timestamp,
                )
            except MigrationFailure as exc:
                exc.path = path
                raise

            migrated_text = yaml.safe_dump(
                migrated_document,
                sort_keys=False,
                allow_unicode=True,
            )
            changes.append(
                MutableV2Change(
                    path=path,
                    original_bytes=original,
                    migrated_bytes=migrated_text.encode("utf-8"),
                    provenance=provenance,
                )
            )

    return MutableV2Plan(changes=changes, skipped=skipped)


def apply_mutable_v2(
    target: Path,
    plan: MutableV2Plan,
    *,
    migrated_at: str | None = None,
) -> Path | None:
    if not plan.changes:
        return None

    import shutil

    timestamp = migrated_at or datetime.now(UTC).isoformat()
    backup_root = target / ".ai-team" / "migration-backups" / MIGRATION_ID
    receipt_entries: list[dict[str, Any]] = []

    for change in plan.changes:
        relative = change.path.relative_to(target)
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(change.path, backup)
        change.path.write_bytes(change.migrated_bytes)
        if change.provenance:
            receipt_entries.append(
                {
                    "path": str(relative).replace("\\", "/"),
                    "timestamps": [
                        {
                            "field": item.field,
                            "value": item.value,
                            "source": item.source,
                        }
                        for item in change.provenance
                    ],
                }
            )

    receipt = {
        "migration_id": MIGRATION_ID,
        "applied_at": timestamp,
        "files_migrated": len(plan.changes),
        "files_skipped_gate_decisions": [str(p.relative_to(target)).replace("\\", "/") for p in plan.skipped],
        "timestamp_provenance": receipt_entries,
    }
    backup_root.mkdir(parents=True, exist_ok=True)
    (backup_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return backup_root
