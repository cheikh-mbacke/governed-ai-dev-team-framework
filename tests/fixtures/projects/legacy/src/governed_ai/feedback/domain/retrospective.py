"""Retrospective identity and status-only review transitions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from governed_ai.feedback import common

VALID_STATUSES = frozenset({"generated", "reviewed"})
NORMATIVE_TRANSITIONS: dict[str, frozenset[str]] = {
    "generated": frozenset({"reviewed"}),
    "reviewed": frozenset(),
}


def revision_of(document: dict[str, Any]) -> int:
    raw = document.get("revision")
    if isinstance(raw, int) and raw >= 1:
        return raw
    return 1


def is_review_allowed(from_status: str) -> bool:
    return "reviewed" in NORMATIVE_TRANSITIONS.get(from_status, frozenset())


def apply_review(
    document: dict[str, Any],
    *,
    reviewed_by: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Transition generated → reviewed without mutating snapshot content.

    Optional `notes` replace the existing notes field only (review annotation).
    All other content fields are preserved byte-for-byte via deepcopy.
    """
    current_status = document.get("status")
    if current_status not in VALID_STATUSES:
        raise ValueError(f"unknown retrospective status {current_status!r}")
    if not is_review_allowed(str(current_status)):
        raise ValueError(
            f"transition from {current_status!r} to 'reviewed' is not allowed"
        )

    updated = deepcopy(document)
    updated["status"] = "reviewed"
    updated["revision"] = revision_of(document) + 1
    updated["reviewed_at"] = common.now_iso()
    if reviewed_by is not None:
        updated["reviewed_by"] = reviewed_by
    if notes is not None:
        updated["notes"] = notes
    return updated
