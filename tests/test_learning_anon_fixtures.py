"""Regression: anonymized cumulative Feedback Exports dedupe correctly."""

from __future__ import annotations

import shutil
from pathlib import Path

from governed_ai.learning.aggregate import build_aggregate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "learning" / "exports"


def test_anonymized_feedback_exports_dedupe_to_unique_observations(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    shutil.copytree(FIXTURES, inbox)
    exports = sorted(inbox.glob("EXP-ANON-*.json"))
    assert len(exports) == 9

    index = build_aggregate(inbox)
    assert index["export_count"] == 9
    # Audit baseline: 86 cumulative rows → 14 unique observation identities.
    assert index["unique_observation_count"] == 14
    assert index["observation_count"] == 14
    assert sum(index["by_category"].values()) == 14
    # Naive sum of occurrence_count across all rows would be far higher; unique
    # latest revision must not inflate actionable rows beyond unique ids.
    assert len(index["actionable_for_framework"]) <= 14
