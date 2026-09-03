"""Feedback domain models."""

from governed_ai.feedback.domain.observation import (
    ALL_STATUSES,
    NORMATIVE_TRANSITIONS,
    TERMINAL_STATUSES,
    UNRESOLVED_STATUSES,
    VALID_CONFIDENCES,
    VALID_ORIGINS,
    apply_coalesce,
    apply_transition,
    find_coalesce_candidate,
    is_transition_allowed,
    iter_forbidden_transitions,
    iter_permitted_transitions,
    normalize_recurrence_key,
    occurrence_count_of,
    revision_of,
)

__all__ = [
    "ALL_STATUSES",
    "NORMATIVE_TRANSITIONS",
    "TERMINAL_STATUSES",
    "UNRESOLVED_STATUSES",
    "VALID_CONFIDENCES",
    "VALID_ORIGINS",
    "apply_coalesce",
    "apply_transition",
    "find_coalesce_candidate",
    "is_transition_allowed",
    "iter_forbidden_transitions",
    "iter_permitted_transitions",
    "normalize_recurrence_key",
    "occurrence_count_of",
    "revision_of",
]
