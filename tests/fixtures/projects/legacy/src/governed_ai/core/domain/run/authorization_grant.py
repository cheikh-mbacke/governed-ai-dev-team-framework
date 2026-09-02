"""RunAuthorizationGrant mechanics (Document 6 §8).

A grant is a human-issued, time/scope-bounded authorization for an entire
unattended Run — distinct from the single-use `human_authorization` token
used for isolated gate decisions (Document 6 §8: reusing that mechanism as-is
"serait un détournement de son modèle de sécurité"). These are pure,
side-effect-free checks; the Core is the only thing allowed to act on them.
"""

from __future__ import annotations

from governed_ai.compat.datetime import UTC, datetime
from typing import Any

# Document 6 §8 — minimum actions a grant can never authorize, regardless of
# what its author requests. "ModifyConstitution"/"ProductionAction" are not
# yet real command types in this codebase, but are listed so a grant can
# never be issued without excluding them once they exist.
MINIMUM_EXCLUDED_ACTIONS = frozenset(
    {
        "RecordGateDecision",
        "RecordAcceptance",
        "ResolveDecisionRequest",
        "ModifyConstitution",
        "ProductionAction",
    }
)


def is_revoked(grant: dict[str, Any]) -> bool:
    return bool(grant.get("revoked_at"))


def is_expired(grant: dict[str, Any], *, now_iso: str) -> bool:
    expires_at = grant.get("expires_at")
    if not expires_at:
        return False
    try:
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        # A malformed expiry must fail closed even if it predates the current
        # schema's date-time validation.
        return True
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return now >= expiry


def is_exhausted(grant: dict[str, Any]) -> bool:
    return grant.get("uses_count", 0) >= grant.get("maximum_uses", 1)


def excludes_action(grant: dict[str, Any], command_type: str) -> bool:
    return command_type in (grant.get("excluded_actions") or [])


def unusable_reason(grant: dict[str, Any], *, now_iso: str, command_type: str) -> str | None:
    """Return why this grant cannot authorize `command_type` right now, or None if it can."""
    if is_revoked(grant):
        return "revoked"
    if is_expired(grant, now_iso=now_iso):
        return "expired"
    if excludes_action(grant, command_type):
        return "excluded_action"
    return None
