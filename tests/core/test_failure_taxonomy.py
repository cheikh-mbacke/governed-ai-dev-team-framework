"""Failure taxonomy classification and systemic signatures (Lot 4)."""

from __future__ import annotations

from governed_ai.core.domain.run.failure_taxonomy import (
    classify_attempt_failure,
    systemic_failure_signature,
)


def test_timeout_is_work_unit_scoped() -> None:
    classified = classify_attempt_failure(
        status="timed_out",
        step="sandbox_implementation",
        summary="agent CLI exceeded 5400s timeout",
    )
    assert classified == {
        "failure_code": "agent_timeout",
        "failure_scope": "work_unit",
        "retryability": "retryable",
    }


def test_agent_timeout_is_not_a_systemic_signature() -> None:
    attempt = {
        "status": "timed_out",
        "step": "sandbox_implementation",
        "summary": "same timeout every time",
        "failure_code": "agent_timeout",
        "failure_scope": "work_unit",
    }
    assert systemic_failure_signature(attempt) is None


def test_adapter_exception_is_systemic() -> None:
    classified = classify_attempt_failure(
        status="blocked",
        step="sandbox_implementation",
        summary="adapter execution failed: RuntimeError: boom",
    )
    assert classified is not None
    assert classified["failure_code"] == "adapter_exception"
    assert classified["failure_scope"] == "adapter"
    attempt = {
        "status": "blocked",
        "step": "sandbox_implementation",
        "summary": "adapter execution failed: RuntimeError: boom",
        **classified,
    }
    assert systemic_failure_signature(attempt) == (
        "taxonomy",
        "adapter_exception",
        "adapter",
    )
