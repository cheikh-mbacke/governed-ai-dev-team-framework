"""Stable failure taxonomy for execution attempts (resilience / convergence)."""

from __future__ import annotations

from typing import Any

SYSTEMIC_FAILURE_SCOPES = frozenset({"adapter", "host", "run"})

FAILURE_CODES = frozenset(
    {
        "agent_timeout",
        "orphan_started",
        "adapter_exception",
        "evidence_gate",
        "execution_boundary",
        "handoff_invalid",
        "agent_failed",
        "agent_blocked",
        "integration_gate",
        "unknown",
    }
)


def classify_attempt_failure(
    *,
    status: str,
    step: str,
    summary: str | None = None,
    limitations: list[str] | None = None,
) -> dict[str, str] | None:
    """Return failure metadata for non-success terminal statuses, else None."""
    if status not in {"failed", "timed_out", "blocked", "cancelled"}:
        return None

    text = " ".join(
        [
            str(summary or ""),
            *[str(item) for item in (limitations or [])],
        ]
    ).lower()

    # Orphan recovery may finalize as timed_out while carrying orphan semantics.
    if "orphan" in text or "interrupted" in text:
        return {
            "failure_code": "orphan_started",
            "failure_scope": "run",
            "retryability": "retryable",
        }
    if status == "timed_out":
        return {
            "failure_code": "agent_timeout",
            "failure_scope": "work_unit",
            "retryability": "retryable",
        }
    if "evidence gate" in text:
        return {
            "failure_code": "evidence_gate",
            "failure_scope": "work_unit",
            "retryability": "retryable_after_change",
        }
    if "execution boundary" in text or "out-of-scope" in text or "out-of-envelope" in text:
        return {
            "failure_code": "execution_boundary",
            "failure_scope": "work_unit",
            "retryability": "non_retryable",
        }
    if "governed json handoff" in text or "handoff" in text:
        return {
            "failure_code": "handoff_invalid",
            "failure_scope": "work_unit",
            "retryability": "retryable",
        }
    if "integration gate" in text:
        return {
            "failure_code": "integration_gate",
            "failure_scope": "work_unit",
            "retryability": "retryable_after_change",
        }
    if status == "blocked" and "adapter execution failed" in text:
        return {
            "failure_code": "adapter_exception",
            "failure_scope": "adapter",
            "retryability": "retryable_after_change",
        }
    if status == "blocked":
        return {
            "failure_code": "agent_blocked",
            "failure_scope": "adapter",
            "retryability": "retryable_after_change",
        }
    if status == "failed":
        return {
            "failure_code": "agent_failed",
            "failure_scope": "work_unit",
            "retryability": "retryable",
        }
    return {
        "failure_code": "unknown",
        "failure_scope": "work_unit",
        "retryability": "retryable_after_change",
    }


def systemic_failure_signature(attempt: dict[str, Any]) -> tuple[str, ...] | None:
    """Return a signature that may stop the whole Run, or None if Work-Unit-local."""
    status = str(attempt.get("status") or "")
    if status not in {"failed", "timed_out", "blocked"}:
        return None
    scope = str(attempt.get("failure_scope") or "")
    code = str(attempt.get("failure_code") or "")
    if scope in SYSTEMIC_FAILURE_SCOPES and code:
        return ("taxonomy", code, scope)
    # Legacy attempts without taxonomy: never treat implementation timeouts as systemic.
    step = str(attempt.get("step") or "")
    if status == "timed_out" and step in {"sandbox_implementation", "remediation"}:
        return None
    if not code and not scope:
        return ("legacy", step, str(attempt.get("summary") or ""))
    return None
