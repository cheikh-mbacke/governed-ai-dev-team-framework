"""execution_ceiling — action-capability ceiling per Work Unit (Document 6 §7).

Separates what a Work Unit *is* (its risk class) from what an agent is
allowed to *do* on it without a human, in the enveloppe autorisée. Every
dimension is one of `allowed` / `conditional` / `forbidden`; two dimensions
are structurally pinned to `forbidden` for every unattended preset, with no
exception (Document 6 §2.4, §9.8): `protected_branch_merge`, `production_action`.
"""

from __future__ import annotations

from typing import Any

CEILING_DIMENSIONS = (
    "analysis",
    "sandbox_implementation",
    "verification",
    "integration_branch_merge",
    "protected_branch_merge",
    "staging_deployment",
    "production_action",
)

CEILING_STATES = frozenset({"allowed", "conditional", "forbidden"})

# Document 6 §2.4/§7.1/§9.8 — never relaxed, for any preset, no exception.
ALWAYS_FORBIDDEN_DIMENSIONS = frozenset({"protected_branch_merge", "production_action"})

_STATE_RANK = {"allowed": 0, "conditional": 1, "forbidden": 2}

DEFAULT_EXECUTION_CEILING: dict[str, str] = {
    "analysis": "allowed",
    "sandbox_implementation": "allowed",
    "verification": "allowed",
    "integration_branch_merge": "conditional",
    "protected_branch_merge": "forbidden",
    "staging_deployment": "forbidden",
    "production_action": "forbidden",
}


def validate_execution_ceiling(ceiling: dict[str, Any]) -> str | None:
    """Return why this ceiling is structurally invalid, or None if it's fine."""
    for dimension in CEILING_DIMENSIONS:
        state = ceiling.get(dimension)
        if state not in CEILING_STATES:
            return f"execution_ceiling.{dimension} must be one of {sorted(CEILING_STATES)}"
    for dimension in ALWAYS_FORBIDDEN_DIMENSIONS:
        if ceiling.get(dimension) != "forbidden":
            return f"execution_ceiling.{dimension} must be forbidden for every unattended preset"
    return None


def capability_for_step(step: str) -> str | None:
    """Return the ceiling dimension a step name refers to, or None for an ordinary step."""
    workflow_capabilities = {
        "review": "verification",
        "security_review": "verification",
        "audit": "verification",
        "remediation": "sandbox_implementation",
    }
    return step if step in CEILING_DIMENSIONS else workflow_capabilities.get(step)


def is_step_permitted(ceiling: dict[str, Any], step: str) -> tuple[bool, str | None]:
    """Return (permitted, blocking_state) for `step` against `ceiling`.

    A step outside the ceiling vocabulary (e.g. "implement", "remediation") is
    always permitted at this layer — the ceiling only governs the seven named
    capabilities, never ordinary implementation work.
    """
    dimension = capability_for_step(step)
    if dimension is None:
        return True, None
    state = ceiling.get(dimension, "forbidden")
    return state == "allowed", state


def can_tighten(current_state: str, new_state: str) -> bool:
    """True only if `new_state` is strictly more restrictive than `current_state`.

    Document 6 §7.3 — escalation is automatic and one-directional; there is no
    corresponding "loosen" path in this codebase, which is how de-escalation
    without human validation is made structurally impossible, not just discouraged.
    """
    return _STATE_RANK.get(new_state, -1) > _STATE_RANK.get(current_state, -1)
