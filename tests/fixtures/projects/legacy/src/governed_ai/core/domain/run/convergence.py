"""Bounded convergence loop enforcement (Document 6 §9.3).

For a Work Unit's execution within a Run, the number of attempts per step
and the number of remediation cycles are capped, and a step whose last two
failures share the same signature is stopped rather than retried blindly.
These bounds are mechanical Core enforcement — an agent proposes another
attempt, the Core decides whether one is still allowed.
"""

from __future__ import annotations

from typing import Any

REMEDIATION_STEP = "remediation"
DEFAULT_MAXIMUM_ATTEMPTS_PER_STEP = 3
DEFAULT_MAXIMUM_REMEDIATION_CYCLES = 2
REPEATED_FAILURE_THRESHOLD = 2

# Every terminal AdapterSPI.RuntimeStatus other than "succeeded" — a blocked,
# cancelled, or timed-out attempt is not a success and counts the same as a
# failure for repeated-failure detection.
NON_SUCCESS_STATUSES = frozenset({"failed", "blocked", "cancelled", "timed_out"})

REASON_IDENTICAL_FAILURE_REPEATED = "identical_failure_repeated"
REASON_REMEDIATION_CYCLES_EXHAUSTED = "remediation_cycles_exhausted"
REASON_STEP_ATTEMPTS_EXHAUSTED = "step_attempts_exhausted"


def attempts_for_step(
    attempts: list[dict[str, Any]], work_unit_id: str, step: str
) -> list[dict[str, Any]]:
    return [
        attempt
        for attempt in attempts
        if attempt.get("work_unit_id") == work_unit_id and attempt.get("step") == step
    ]


def _repeated_identical_failure(attempts: list[dict[str, Any]]) -> bool:
    failed = [a for a in attempts if a.get("status") in NON_SUCCESS_STATUSES and a.get("summary")]
    if len(failed) < REPEATED_FAILURE_THRESHOLD:
        return False
    last = failed[-REPEATED_FAILURE_THRESHOLD:]
    return len({a["summary"] for a in last}) == 1


def convergence_exhaustion_reason(
    step_attempts: list[dict[str, Any]],
    *,
    step: str,
    maximum_attempts_per_step: int,
    maximum_remediation_cycles: int,
) -> str | None:
    """Return why this step's convergence loop must stop, or None if another attempt is allowed."""
    if _repeated_identical_failure(step_attempts):
        return REASON_IDENTICAL_FAILURE_REPEATED
    if step == REMEDIATION_STEP and len(step_attempts) >= maximum_remediation_cycles:
        return REASON_REMEDIATION_CYCLES_EXHAUSTED
    if len(step_attempts) >= maximum_attempts_per_step:
        return REASON_STEP_ATTEMPTS_EXHAUSTED
    return None
