"""Unit tests for orchestrator auto-observation classification."""

from __future__ import annotations

from governed_ai.feedback.domain.auto_observation import classify_auto_observation


def test_classify_failed_sandbox_implementation() -> None:
    fields = classify_auto_observation(step="sandbox_implementation", status="failed")
    assert fields["category"] == "tooling"
    assert fields["classification"] == {"origin": "framework", "confidence": "low"}
    assert "Triage" in (fields["candidate_improvement"] or "")


def test_classify_timed_out_verification() -> None:
    fields = classify_auto_observation(step="verification", status="timed_out")
    assert fields["category"] == "testing"
    assert fields["classification"]["origin"] == "framework"
    assert fields["classification"]["confidence"] == "probable"


def test_classify_blocked_review() -> None:
    fields = classify_auto_observation(step="review", status="blocked")
    assert fields["category"] == "review"
    assert fields["classification"] == {"origin": "human_process", "confidence": "probable"}
