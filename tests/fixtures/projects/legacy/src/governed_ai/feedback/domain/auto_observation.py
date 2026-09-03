"""Classify orchestrator-emitted auto Observations for framework learning."""

from __future__ import annotations

from typing import Any

# Map dispatch step → Observation.category so auto signals are actionable
# in by_category aggregates (not a generic "orchestration" bucket for all steps).
STEP_CATEGORY: dict[str, str] = {
    "sandbox_implementation": "tooling",
    "remediation": "tooling",
    "verification": "testing",
    "review": "review",
    "security_review": "audit",
    "audit": "audit",
    "integration_review": "orchestration",
}

_STATUS_ORIGIN: dict[str, tuple[str, str]] = {
    # Framework loop friction (timeouts/cancels are orchestrator-side).
    "timed_out": ("framework", "probable"),
    "cancelled": ("framework", "probable"),
    # Blocked usually waits on a human gate or external unblock.
    "blocked": ("human_process", "probable"),
    # Failed attempts are recorded by the framework loop; root cause may be
    # project-side, so confidence stays low until a human reclassifies.
    "failed": ("framework", "low"),
}


def classify_auto_observation(*, step: str, status: str) -> dict[str, Any]:
    """Return RecordObservation payload fields for an orchestrator auto signal."""
    category = STEP_CATEGORY.get(step, "orchestration")
    origin, confidence = _STATUS_ORIGIN.get(status, ("framework", "low"))
    improvement = {
        "failed": (
            f"Triage recurring auto:{step}:failed signals; "
            "confirm whether root cause is framework, project, or environment"
        ),
        "timed_out": (
            f"Review worker stall / timeout thresholds and step duration for {step!r}"
        ),
        "blocked": (
            f"Clarify unblocking path or human gate for step {step!r}"
        ),
        "cancelled": (
            f"Investigate why step {step!r} was cancelled mid-run"
        ),
    }.get(status)

    return {
        "category": category,
        "classification": {"origin": origin, "confidence": confidence},
        "candidate_improvement": improvement,
    }
