"""Distribution installation record migration tests (Document 14 DI-003)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from distribution.installer import (
    INSTALLATION_RECORD_FILE,
    LEGACY_VERSION_FILE,
    MigrationError,
    is_v2_record,
    load_installation_record,
    managed_files_union,
    migrate_v1_to_v2,
)
from distribution.installer.ownership import classify_managed_file

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_WITNESS = REPO_ROOT / "tests" / "fixtures" / "projects" / "legacy"
GOLDEN_V1 = REPO_ROOT / "tests" / "fixtures" / "legacy-0.4" / "objects" / "installation-manifest.json"


def _copy_legacy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "legacy-project"
    shutil.copytree(LEGACY_WITNESS, target)
    return target


def _load_profile(target: Path) -> dict:
    return yaml.safe_load(
        (target / ".ai-team" / "project-profile.yaml").read_text(encoding="utf-8")
    )


def test_di003_legacy_fixture_preserves_all_managed_files(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    v1 = json.loads((target / LEGACY_VERSION_FILE).read_text(encoding="utf-8"))
    original_managed = set(v1["managed_files"])

    result = migrate_v1_to_v2(target, migrated_at="2026-08-29T20:20:00+00:00")

    assert is_v2_record(result.record)
    migrated = managed_files_union(result.record)
    migrated.discard(INSTALLATION_RECORD_FILE.as_posix())
    assert migrated == original_managed
    assert (target / INSTALLATION_RECORD_FILE).is_file()
    profile = _load_profile(target)
    assert profile.get("active_adapter_id") == "cursor"


def test_migration_creates_backup_in_migration_backups(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    result = migrate_v1_to_v2(target, migrated_at="2026-08-29T20:21:00+00:00")
    assert result.backup_path.is_file()
    assert result.backup_path.parent.as_posix().endswith(".ai-team/migration-backups")
    backup_payload = json.loads(result.backup_path.read_text(encoding="utf-8"))
    assert backup_payload["schema_version"] == 1


def test_unclassifiable_managed_file_blocks_migration(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    manifest_path = target / LEGACY_VERSION_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["managed_files"] = list(manifest["managed_files"]) + ["mystery/unowned.bin"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(MigrationError) as exc_info:
        migrate_v1_to_v2(target)

    assert exc_info.value.code == "UNCLASSIFIABLE_MANAGED_FILE"

    assert not (target / INSTALLATION_RECORD_FILE).exists()
    assert load_installation_record(target) is None


def test_unknown_active_adapter_id_blocks_migration(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    profile_path = target / ".ai-team" / "project-profile.yaml"
    profile = _load_profile(target)
    profile["active_adapter_id"] = "codex"
    profile_path.write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(MigrationError) as exc_info:
        migrate_v1_to_v2(target)

    assert exc_info.value.code == "UNKNOWN_ACTIVE_ADAPTER"


def test_legacy_adapter_form_sets_active_adapter_id(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    profile_path = target / ".ai-team" / "project-profile.yaml"
    profile = _load_profile(target)
    profile.pop("active_adapter_id", None)
    profile["adapter"] = {"id": "cursor", "version": "0.4.0"}
    profile_path.write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    migrate_v1_to_v2(target, migrated_at="2026-08-29T20:22:00+00:00")
    updated = _load_profile(target)
    assert updated.get("active_adapter_id") == "cursor"


def test_legacy_adapter_version_mismatch_blocks(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    profile_path = target / ".ai-team" / "project-profile.yaml"
    profile = _load_profile(target)
    profile["adapter"] = {"id": "cursor", "version": "9.9.9"}
    profile_path.write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(MigrationError) as exc_info:
        migrate_v1_to_v2(target)

    assert exc_info.value.code == "ADAPTER_VERSION_MISMATCH"


def test_migration_040_to_050_updates_component_versions(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    result = migrate_v1_to_v2(
        target,
        migrated_at="2026-08-29T20:23:00+00:00",
        target_version="0.5.0",
    )
    record = result.record
    assert record["core"]["version"] == "0.5.0"
    assert record["distribution"]["version"] == "0.5.0"
    assert record["adapters"][0]["version"] == "0.5.0"


def test_v2_record_has_expected_owner_buckets(tmp_path: Path) -> None:
    target = _copy_legacy_fixture(tmp_path)
    result = migrate_v1_to_v2(target, migrated_at="2026-08-29T20:24:00+00:00")
    record = result.record
    core_files = set(record["core"]["managed_files"])
    cursor_files = set(record["adapters"][0]["managed_files"])
    distribution_files = set(record["distribution"]["managed_files"])

    assert ".cursor/hooks.json" in cursor_files
    assert ".ai-team/schemas/work-unit.schema.json" in core_files
    assert INSTALLATION_RECORD_FILE.as_posix() in distribution_files
    assert all(classify_managed_file(path) == "core" for path in core_files)
    assert all(classify_managed_file(path) == "adapter:cursor" for path in cursor_files)


def test_golden_v1_subset_classifies_and_builds_record(tmp_path: Path) -> None:
    target = tmp_path / "golden"
    (target / ".ai-team").mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / ".ai-team" / "project-profile.yaml",
        target / ".ai-team" / "project-profile.yaml",
    )
    golden = json.loads(GOLDEN_V1.read_text(encoding="utf-8"))
    (target / LEGACY_VERSION_FILE).write_text(
        json.dumps(golden, indent=2) + "\n",
        encoding="utf-8",
    )

    result = migrate_v1_to_v2(target, migrated_at="2026-08-29T20:25:00+00:00")
    migrated = managed_files_union(result.record)
    migrated.discard(INSTALLATION_RECORD_FILE.as_posix())
    assert migrated == set(golden["managed_files"])
