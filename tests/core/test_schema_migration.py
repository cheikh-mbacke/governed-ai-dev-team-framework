"""WU-P3-SCHEMA-V2 — mutable schema v2 migration (MIG-001, MIG-002)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from governed_ai.core.persistence.migrations.legacy_gate import (
    is_gate_decision_document,
    read_gate_decision,
)
from governed_ai.core.persistence.migrations.mutable_v2 import (
    MIGRATION_ID,
    MigrationFailure,
    apply_mutable_v2,
    plan_mutable_v2,
)

from tests.core.workspace_helpers import PAYLOAD_AI_TEAM

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATED_AT = "2026-08-29T19:00:00+00:00"


def _seed_ai_team(tmp_path: Path) -> Path:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    shutil.copytree(source / "schemas", ai_team / "schemas")
    for directory in (
        "work-units",
        "decisions",
        "findings",
        "acceptance",
        "release-candidates",
    ):
        (ai_team / directory).mkdir(parents=True)
    return ai_team


def _legacy_work_unit() -> dict:
    return {
        "id": "WU-MIG-001",
        "title": "Migration test",
        "objective": {"result": "ok"},
        "scope": {"include": [], "exclude": []},
        "expected_behavior": "migrate",
        "acceptance_criteria": ["ok"],
        "dependencies": [],
        "risk": {"class": "low"},
        "required_verification": {"unit_tests": True},
        "status": "ready",
    }


@pytest.fixture()
def migration_workspace(tmp_path: Path) -> Path:
    _seed_ai_team(tmp_path)
    return tmp_path


def test_mig_001_assigns_revision_and_timestamps_with_provenance(
    migration_workspace: Path,
) -> None:
    """MIG-001 — legacy object without v2 fields migrates deterministically."""
    wu_path = migration_workspace / ".ai-team" / "work-units" / "WU-MIG-001.yaml"
    original = yaml.safe_dump(_legacy_work_unit(), sort_keys=False)
    wu_path.write_text(original, encoding="utf-8")

    plan = plan_mutable_v2(migration_workspace, migrated_at=MIGRATED_AT)
    assert len(plan.changes) == 1

    backup_root = apply_mutable_v2(
        migration_workspace,
        plan,
        migrated_at=MIGRATED_AT,
    )
    assert backup_root is not None

    migrated = yaml.safe_load(wu_path.read_text(encoding="utf-8"))
    assert migrated["revision"] == 1
    assert migrated["created_at"] == MIGRATED_AT
    assert migrated["updated_at"] == MIGRATED_AT
    assert migrated["title"] == "Migration test"

    receipt = json.loads((backup_root / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["migration_id"] == MIGRATION_ID
    assert receipt["timestamp_provenance"]
    assert receipt["timestamp_provenance"][0]["timestamps"][0]["source"] == (
        f"migration:{MIGRATION_ID}"
    )

    backup = backup_root / ".ai-team" / "work-units" / "WU-MIG-001.yaml"
    assert yaml.safe_load(backup.read_text(encoding="utf-8")) == _legacy_work_unit()


def test_mig_002_stops_when_required_business_field_missing(
    migration_workspace: Path,
) -> None:
    """MIG-002 — migration stops without inventing missing business values."""
    invalid = _legacy_work_unit()
    del invalid["title"]
    wu_path = migration_workspace / ".ai-team" / "work-units" / "WU-MIG-002.yaml"
    original = yaml.safe_dump(invalid, sort_keys=False)
    wu_path.write_text(original, encoding="utf-8")

    with pytest.raises(MigrationFailure, match="title"):
        plan_mutable_v2(migration_workspace, migrated_at=MIGRATED_AT)

    assert wu_path.read_text(encoding="utf-8") == original
    assert not list((migration_workspace / ".ai-team" / "migration-backups").glob("**/*"))


def test_legacy_gate_decisions_are_skipped_not_rewritten(migration_workspace: Path) -> None:
    gate_path = migration_workspace / ".ai-team" / "decisions" / "gate-g1-test.yaml"
    gate_document = {
        "id": "gate-g1-test",
        "gate": "G1",
        "status": "approved",
        "by": "test-human",
        "at": "2026-01-01T00:00:00+00:00",
        "note": "legacy audit",
    }
    original = yaml.safe_dump(gate_document, sort_keys=False)
    gate_path.write_text(original, encoding="utf-8")

    plan = plan_mutable_v2(migration_workspace, migrated_at=MIGRATED_AT)
    assert plan.changes == []
    assert gate_path in plan.skipped

    apply_mutable_v2(migration_workspace, plan, migrated_at=MIGRATED_AT)
    assert gate_path.read_text(encoding="utf-8") == original
    assert read_gate_decision(gate_path)["gate"] == "G1"
    assert is_gate_decision_document(yaml.safe_load(original))


def test_existing_timestamps_are_preserved(migration_workspace: Path) -> None:
    document = _legacy_work_unit()
    document["created_at"] = "2026-01-01T00:00:00+00:00"
    wu_path = migration_workspace / ".ai-team" / "work-units" / "WU-MIG-003.yaml"
    wu_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    plan = plan_mutable_v2(migration_workspace, migrated_at=MIGRATED_AT)
    apply_mutable_v2(migration_workspace, plan, migrated_at=MIGRATED_AT)

    migrated = yaml.safe_load(wu_path.read_text(encoding="utf-8"))
    assert migrated["created_at"] == "2026-01-01T00:00:00+00:00"
    assert migrated["updated_at"] == MIGRATED_AT
    assert migrated["revision"] == 1
