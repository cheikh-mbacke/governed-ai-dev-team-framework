"""Observation transition state machine unit tests."""

from __future__ import annotations

import pytest

from governed_ai.feedback.domain.observation import (
    apply_transition,
    is_transition_allowed,
    iter_forbidden_transitions,
    iter_permitted_transitions,
)


def test_permitted_transitions_are_forward_only() -> None:
    permitted = set(iter_permitted_transitions())
    assert ("open", "acknowledged") in permitted
    assert ("open", "resolved") in permitted
    assert ("acknowledged", "candidate_change") in permitted
    assert ("candidate_change", "rejected") in permitted
    assert ("resolved", "open") not in permitted
    assert ("rejected", "acknowledged") not in permitted


def test_forbidden_transitions_include_terminal_exits() -> None:
    forbidden = set(iter_forbidden_transitions())
    assert ("resolved", "acknowledged") in forbidden
    assert ("rejected", "candidate_change") in forbidden
    assert not is_transition_allowed("resolved", "open")


def test_apply_transition_requires_resolution_for_terminal() -> None:
    document = {"id": "OBS-1", "status": "open", "revision": 1}
    with pytest.raises(ValueError, match="resolution"):
        apply_transition(document, to_status="resolved")


def test_apply_transition_updates_classification_and_revision() -> None:
    document = {
        "id": "OBS-1",
        "status": "open",
        "revision": 1,
        "classification": {"origin": "unknown", "confidence": "low"},
    }
    updated = apply_transition(
        document,
        to_status="acknowledged",
        origin="framework",
        confidence="probable",
    )
    assert updated["status"] == "acknowledged"
    assert updated["revision"] == 2
    assert updated["classification"] == {"origin": "framework", "confidence": "probable"}
    assert document["status"] == "open"
