"""Normative Run state machine (Document 6 §9.1)."""

from __future__ import annotations

from itertools import product

NORMATIVE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"active", "stopped"}),
    "active": frozenset({"completed", "stopped", "failed"}),
    "completed": frozenset(),
    "stopped": frozenset(),
    "failed": frozenset(),
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
