"""Regression: anonymized cumulative Feedback Exports preserve relations + dedupe."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from governed_ai.learning.aggregate import build_aggregate

LEARNING = Path(__file__).resolve().parent / "fixtures" / "learning"
FIXTURES = LEARNING / "exports"
MANIFEST = LEARNING / "MANIFEST.json"


def test_anonymized_fixtures_live_outside_project_witnesses() -> None:
    assert "projects/clean" not in FIXTURES.as_posix()
    assert "projects/legacy" not in FIXTURES.as_posix()
    assert FIXTURES.is_dir()
    assert MANIFEST.is_file()


def test_anonymized_feedback_exports_preserve_relations_and_dedupe(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    shutil.copytree(FIXTURES, inbox)
    exports = sorted(inbox.glob("EXP-ANON-*.json"))
    assert len(exports) == 9

    sequences = []
    by_id: dict[str, list[tuple[int, str]]] = defaultdict(list)
    recurrence = Counter()
    sensitive_hits: list[str] = []
    for path in exports:
        document = json.loads(path.read_text(encoding="utf-8"))
        sequences.append(document["snapshot_sequence"])
        blob = path.read_text(encoding="utf-8").lower()
        for needle in (
            "sads-ecosystem",
            "c:\\users",
            "/home/",
            "agent_transcript",
            "api_key",
            '"provider"',
        ):
            if needle in blob:
                sensitive_hits.append(f"{path.name}:{needle}")
        for row in document.get("observations") or []:
            obs_id = str(row["id"])
            by_id[obs_id].append((int(row.get("revision") or 1), str(row.get("last_recorded_at") or "")))
            if row.get("recurrence_key"):
                recurrence[str(row["recurrence_key"])] += 1

    assert sensitive_hits == []
    assert sequences == list(range(1, 10))
    assert any(len(versions) > 1 for versions in by_id.values()), "expected cross-snapshot duplicates"
    assert any(key.startswith("auto:") for key in recurrence), "expected auto: recurrence keys"

    index = build_aggregate(inbox)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert index["export_count"] == manifest["baseline"]["export_count"] == 9
    assert index["unique_observation_count"] == manifest["baseline"]["unique_observation_ids"] == 14
    assert index["observation_count"] == 14
    assert sum(index["by_category"].values()) == 14
    assert len(index["actionable_for_framework"]) <= 14
