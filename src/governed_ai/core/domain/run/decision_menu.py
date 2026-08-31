"""Decision-menu structured matching and deterministic validation (Document 6 §5).

"Le levier central" (§5.1): a `mandate-matcher` observes a fork and proposes
a correspondence with a `decision-menu` entry — it never decides. Only this
module's checks, run by the Core, can turn that proposal into an automatic
resolution. No natural-language interpretation is involved anywhere here.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from typing import Any

REASON_TRIGGER_MISMATCH = "trigger_mismatch"
REASON_OUT_OF_SCOPE_WORK_UNIT = "out_of_scope_work_unit"
REASON_OUT_OF_SCOPE_ENVIRONMENT = "out_of_scope_environment"
REASON_EXPIRED = "expired"
REASON_MAXIMUM_USES_REACHED = "maximum_uses_reached"
REASON_MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"


def trigger_matches(entry_trigger: dict[str, Any], observed_trigger: dict[str, Any]) -> bool:
    """Compare typed trigger fields mechanically (Document 6 §5.2 example).

    Top-level keys other than ``conditions`` (e.g. ``type``, ``package_category``)
    must match exactly. Nested ``conditions`` are checked key-by-key.
    """
    if entry_trigger.get("type") != observed_trigger.get("type"):
        return False
    for key, expected in entry_trigger.items():
        if key in {"type", "conditions"}:
            continue
        if observed_trigger.get(key) != expected:
            return False
    conditions = entry_trigger.get("conditions") or {}
    for key, expected in conditions.items():
        observed_conditions = observed_trigger.get("conditions")
        if isinstance(observed_conditions, dict) and key in observed_conditions:
            if observed_conditions.get(key) != expected:
                return False
            continue
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
    if expires_at:
        try:
            now = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if now.tzinfo is None:
                now = now.replace(tzinfo=UTC)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
        except ValueError:
            return REASON_EXPIRED
        if now >= expiry:
            return REASON_EXPIRED
    if entry.get("uses_count", 0) >= entry.get("maximum_uses", 1):
        return REASON_MAXIMUM_USES_REACHED
    required_evidence = set(entry.get("required_evidence") or [])
    if not required_evidence.issubset(set(evidence or [])):
        return REASON_MISSING_REQUIRED_EVIDENCE
    return None
