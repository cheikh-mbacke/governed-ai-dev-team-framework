"""Mission artifacts and their adversarial challenge review (Document 6 §6).

Six typed artifacts (`mission_contract`, `acceptance_oracle`, `decision_menu`, `tradeoff_policy`,
`execution_envelope`, `delivery_contract`) are prepared before a human approves
an unattended session's grant. Document 6 §6.2 requires each to survive an
independent adversarial review before it counts toward G1 — "independent"
means the reviewer is mechanically forbidden from being whoever authored the
artifact, never something trusted on say-so. These are pure, side-effect-free
checks; the Core is the only thing allowed to act on them.
"""

from __future__ import annotations

import hashlib
from typing import Any

from governed_ai.contracts.bundle_hash import canonical_json_bytes

MISSION_ARTIFACT_KINDS = frozenset(
    {
        "mission_contract",
        "acceptance_oracle",
        "decision_menu",
        "tradeoff_policy",
        "execution_envelope",
        "delivery_contract",
    }
)

# Document 6 §6.1 — the fields each kind's content must carry. Checked in the
# handler (not the JSON schema) because the shape of `content` genuinely
# differs per kind, and these are still human-drafted/editable documents.
REQUIRED_CONTENT_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "mission_contract": (
        "problem",
        "users",
        "observable_objective",
        "scope_include",
        "scope_exclude",
        "business_rules",
        "invariants",
    ),
    "acceptance_oracle": (
        "nominal_scenarios",
        "error_scenarios",
        "boundary_scenarios",
        "forbidden_outcomes",
    ),
    "decision_menu": ("entries", "anticipated_forks", "coverage_percent"),
    "tradeoff_policy": ("priority_order",),
    "execution_envelope": (
        "environments",
        "network",
        "allowed_dependencies",
        "accessible_secrets",
        "allowed_paths",
        "allowed_commands",
        "budgets",
        "execution_ceilings_by_work_unit",
    ),
    "delivery_contract": (
        "deliverable_definition",
        "rollback_criteria",
        "required_evidence",
    ),
}

CHALLENGE_OUTCOMES = frozenset({"approved", "changes_requested"})


def missing_content_fields(kind: str, content: dict[str, Any]) -> list[str]:
    required = REQUIRED_CONTENT_FIELDS_BY_KIND.get(kind, ())
    return [field for field in required if field not in content]


def can_challenge(*, authored_by_role: str, challenger_role: str) -> bool:
    """§6.2 — a role can never be the sole judge of its own artifact."""
    return authored_by_role != challenger_role


def is_approved(artifact: dict[str, Any]) -> bool:
    return artifact.get("challenge_status") == "approved"


def compute_mission_contract_hash(artifacts: list[dict[str, Any]]) -> str:
    """§8 — grant carries the hash of every approved artifact it relies on."""
    digest = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: item["id"]):
        digest.update(canonical_json_bytes({"id": artifact["id"], "content": artifact["content"]}))
    return f"sha256:{digest.hexdigest()}"


def compute_artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {
        "id": artifact["id"],
        "kind": artifact["kind"],
        "revision": artifact["revision"],
        "content": artifact["content"],
    }
    return f"sha256:{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"
