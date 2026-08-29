"""Rollback tests (Document 13 §11, Document 14 DI-014)."""

from __future__ import annotations

import json
from pathlib import Path

from distribution.installer.snapshot import (
    create_snapshot,
    load_snapshot_manifest,
    restore_snapshot,
    sha256_file,
)


def test_snapshot_manifest_records_hashes_and_restore(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    managed = target / ".ai-team" / "schemas"
    managed.mkdir(parents=True)
    schema = managed / "work-unit.schema.json"
    schema.write_text('{"title": "work-unit"}\n', encoding="utf-8")
    original_hash = sha256_file(schema)

    backup_root = tmp_path / "backup"
    snapshot = create_snapshot(target, [schema], backup_root)
    assert snapshot.manifest_path.is_file()

    schema.write_text('{"title": "mutated"}\n', encoding="utf-8")
    assert sha256_file(schema) != original_hash

    loaded = load_snapshot_manifest(backup_root)
    restore_snapshot(loaded, target, backup_root)
    assert sha256_file(schema) == original_hash

    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert manifest["entries"][0]["sha256"] == original_hash
    assert manifest["entries"][0]["owner"] == "core"
