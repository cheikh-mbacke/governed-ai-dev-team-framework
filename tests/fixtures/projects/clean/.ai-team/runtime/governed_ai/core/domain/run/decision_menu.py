"""Decision-menu structured matching and deterministic validation (Document 6 §5).

"Le levier central" (§5.1): a `mandate-matcher` observes a fork and proposes
a correspondence with a `decision-menu` entry — it never decides. Only this
module's checks, run by the Core, can turn that proposal into an automatic
resolution. No natural-language interpretation is involved anywhere here.
"""

from __future__ import annotations

import fnmatch
from typing import Any

REASON_TRIGGER_MISMATCH = "trigger_mismatch"
REASON_OUT_OF_SCOPE_WORK_UNIT = "out_of_scope_work_unit"
REASON_OUT_OF_SCOPE_ENVIRONMENT = "out_of_scope_environment"
REASON_EXPIRED = "expired"
REASON_MAXIMUM_USES_REACHED = "maximum_uses_reached"
REASON_MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"


def trigger_matches(entry_trigger: dict[str, Any], observed_trigger: dict[str, Any]) -> bool:
    if entry_trigger.get("type") != observed_trigger.get("type"):
        return False
    conditions = entry_trigger.get("conditions") or {}
    for key, expected in conditions.items():
        if observed_trigger.get(key) != expected:
            return False
    return True


def _scope_covers(patterns: list[str] | None, value: str | None) -> bool:
    if not patterns:
        return True
    if value is None:
        return False
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def validate_entry_usable(
    entry: dict[str, Any],
    *,
    trigger: dict[str, Any],
    work_unit_id: str,
    environment: str | None,
    now_iso: str,
    evidence: list[str],
) -> str | None:
    """Return why this decision-menu entry cannot resolve this fork now, or None if it can."""
    if not trigger_matches(entry.get("trigger") or {}, trigger):
        return REASON_TRIGGER_MISMATCH
    scope = entry.get("scope") or {}
    if not _scope_covers(scope.get("work_units"), work_unit_id):
        return REASON_OUT_OF_SCOPE_WORK_UNIT
    if scope.get("environments") and not _scope_covers(scope.get("environments"), environment):
        return REASON_OUT_OF_SCOPE_ENVIRONMENT
    expires_at = entry.get("expires_at")
    if expires_at and now_iso > expires_at:
        return REASON_EXPIRED
    if entry.get("uses_count", 0) >= entry.get("maximum_uses", 1):
        return REASON_MAXIMUM_USES_REACHED
    required_evidence = set(entry.get("required_evidence") or [])
    if not required_evidence.issubset(set(evidence or [])):
        return REASON_MISSING_REQUIRED_EVIDENCE
    return None
