"""Ingest + learning aggregate for consented Feedback Exports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai-team"))

from governed_ai.learning.aggregate import build_aggregate, write_aggregate  # noqa: E402
from ingest_feedback import ingest_document  # noqa: E402


def _minimal_export(*, export_id: str = "EXP-LEARN-001") -> dict:
    return {
        "format_version": "1.2",
        "export_id": export_id,
        "generated_at": "2026-09-03T10:00:00+00:00",
        "detail_level": "full",
        "project_ref": "PRJ-" + ("b" * 32),
        "project_id": "learn-test",
        "framework_version": "0.7.0",
        "constitution_version": "1.1.0",
        "summary": {
            "total": 1,
            "open": 1,
            "by_category": {"tooling": 1},
            "by_origin": {"framework": 1},
            "by_severity": {"medium": 1},
        },
        "observations": [
            {
                "id": "OBS-LEARN-001",
                "recorded_at": "2026-09-03T09:00:00+00:00",
                "project_id": "learn-test",
                "framework_version": "0.7.0",
                "constitution_version": "1.1.0",
                "category": "tooling",
                "severity": "high",
                "symptom": "auto friction",
                "classification": {"origin": "framework", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": True,
                    "human_intervention": False,
                },
                "status": "open",
                "recurrence_key": "auto:sandbox_implementation:failed",
                "occurrence_count": 2,
                "candidate_improvement": "Triage recurring auto signals",
            }
        ],
        "retrospectives": [],
        "executions": [],
    }


def test_ingest_document_writes_inbox_and_aggregate(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    path = ingest_document(_minimal_export(), inbox=inbox)
    assert path.is_file()
    assert path.name == "EXP-LEARN-001.json"
    aggregate_path = tmp_path / "aggregate" / "latest.json"
    assert aggregate_path.is_file()
    index = json.loads(aggregate_path.read_text(encoding="utf-8"))
    assert index["export_count"] == 1
    assert index["observation_count"] == 1
    assert index["by_category"]["tooling"] == 1
    assert index["by_recurrence_key"]["auto:sandbox_implementation:failed"] == 1
    assert index["actionable_for_framework"]


def test_ingest_is_idempotent_for_same_export_id(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    first = ingest_document(_minimal_export(), inbox=inbox)
    second = ingest_document(_minimal_export(), inbox=inbox)
    assert first == second
    assert len(list(inbox.glob("EXP-*.json"))) == 1


def test_ingest_rejects_invalid_payload(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid feedback payload"):
        ingest_document({"export_id": "EXP-BAD"}, inbox=tmp_path / "inbox")


def test_build_aggregate_from_summary_only_export(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    document = _minimal_export(export_id="EXP-AGG-ONLY")
    document["observations"] = []
    document["detail_level"] = "aggregate"
    (inbox / "EXP-AGG-ONLY.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    index = build_aggregate(inbox)
    assert index["export_count"] == 1
    assert index["by_category"]["tooling"] == 1
    result = write_aggregate(inbox=inbox, output=tmp_path / "out.json")
    assert result.export_count == 1
    assert result.index_path.is_file()


def test_build_aggregate_dedups_cumulative_observation_snapshots(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    first = _minimal_export(export_id="EXP-DUP-1")
    first["observations"][0]["revision"] = 1
    first["observations"][0]["occurrence_count"] = 1
    first["observations"][0]["symptom"] = "old"
    second = _minimal_export(export_id="EXP-DUP-2")
    second["generated_at"] = "2026-09-04T10:00:00+00:00"
    second["observations"][0]["revision"] = 3
    second["observations"][0]["occurrence_count"] = 4
    second["observations"][0]["symptom"] = "latest"
    second["observations"][0]["last_recorded_at"] = "2026-09-04T09:00:00+00:00"
    (inbox / "EXP-DUP-1.json").write_text(json.dumps(first), encoding="utf-8")
    (inbox / "EXP-DUP-2.json").write_text(json.dumps(second), encoding="utf-8")

    index = build_aggregate(inbox)
    assert index["export_count"] == 2
    assert index["observation_count"] == 1
    assert index["unique_observation_count"] == 1
    assert index["by_category"]["tooling"] == 1
    assert index["by_recurrence_key"]["auto:sandbox_implementation:failed"] == 1
    assert index["actionable_for_framework"][0]["symptom"] == "latest"
    assert index["actionable_for_framework"][0]["occurrence_count"] == 4
    assert index["actionable_for_framework"][0]["revision"] == 3


def test_build_aggregate_summary_only_keeps_latest_per_project(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    older = _minimal_export(export_id="EXP-SUM-1")
    older["observations"] = []
    older["detail_level"] = "aggregate"
    older["summary"]["total"] = 5
    older["summary"]["by_category"] = {"tooling": 5}
    newer = _minimal_export(export_id="EXP-SUM-2")
    newer["observations"] = []
    newer["detail_level"] = "aggregate"
    newer["generated_at"] = "2026-09-05T10:00:00+00:00"
    newer["summary"]["total"] = 2
    newer["summary"]["by_category"] = {"tooling": 2}
    (inbox / "EXP-SUM-1.json").write_text(json.dumps(older), encoding="utf-8")
    (inbox / "EXP-SUM-2.json").write_text(json.dumps(newer), encoding="utf-8")

    index = build_aggregate(inbox)
    assert index["observation_count"] == 2
    assert index["by_category"]["tooling"] == 2
