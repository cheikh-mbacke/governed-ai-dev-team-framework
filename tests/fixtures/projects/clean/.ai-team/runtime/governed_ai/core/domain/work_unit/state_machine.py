"""Normative Work Unit state machine (Document 14 §6)."""

from __future__ import annotations

from itertools import product

NORMATIVE_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset(
        {"verification", "waiting_decision", "blocked", "ready", "cancelled"}
    ),
    "waiting_decision": frozenset({"in_progress", "blocked", "cancelled"}),
    "blocked": frozenset({"in_progress", "ready", "cancelled"}),
    "verification": frozenset(
        {"review", "in_progress", "remediation_required", "done", "cancelled"}
    ),
    "review": frozenset(
        {"audit", "verification", "remediation_required", "done", "cancelled"}
    ),
    "audit": frozenset(
        {"human_test", "verification", "remediation_required", "done", "cancelled"}
    ),
    "human_test": frozenset(
        {"done", "remediation_required", "verification", "cancelled"}
    ),
    "remediation_required": frozenset({"in_progress", "cancelled"}),
    "done": frozenset(),
    "cancelled": frozenset(),
}

ALL_STATUSES = frozenset(NORMATIVE_TRANSITIONS)


def allowed_targets(from_status: str) -> frozenset[str]:
    return NORMATIVE_TRANSITIONS.get(from_status, frozenset())


def is_transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in allowed_targets(from_status)


def iter_permitted_transitions() -> list[tuple[str, str]]:
    return sorted(
        (from_status, to_status)
        for from_status, targets in NORMATIVE_TRANSITIONS.items()
        for to_status in targets
    )


def iter_forbidden_transitions() -> list[tuple[str, str]]:
    forbidden: list[tuple[str, str]] = []
    for from_status, to_status in product(ALL_STATUSES, ALL_STATUSES):
        if from_status == to_status:
            continue
        if not is_transition_allowed(from_status, to_status):
            forbidden.append((from_status, to_status))
    return sorted(forbidden)
