"""Decision Request state machine (Document 14 §6)."""

from __future__ import annotations

from itertools import product

NORMATIVE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending_human": frozenset({"decided", "cancelled"}),
    "decided": frozenset(),
    "cancelled": frozenset(),
}

ALL_STATUSES = frozenset(NORMATIVE_TRANSITIONS)


def is_transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in NORMATIVE_TRANSITIONS.get(from_status, frozenset())


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
