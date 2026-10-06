"""Plan Work Units for a multi-member ensemble (Document 25 Phase 5)."""

from __future__ import annotations

from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.workspace import Workspace


def _declared_member_ids(workspace: Workspace) -> list[str]:
    return [entry["id"] for entry in workspace.declared_members()]


def enforce_ensemble_work_unit(workspace: Workspace, document: dict[str, Any]) -> None:
    """Reject product Work Units that omit member_id on a 2+ member ensemble."""
    member_ids = _declared_member_ids(workspace)
    if len(member_ids) < 2:
        return
    kind = document.get("kind")
    member_id = document.get("member_id")
    if kind == "integration":
        if member_id:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "integration work units must not set member_id",
                "/payload/member_id",
            )
        includes = ((document.get("scope") or {}).get("include")) or []
        if includes:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "integration work units must not include product paths",
                "/payload/scope/include",
            )
        return
    if not isinstance(member_id, str) or member_id not in member_ids:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "member_id is required and must be a declared ensemble member "
            "when the ensemble has two or more members",
            "/payload/member_id",
        )


def plan_ensemble_work_units(workspace: Workspace) -> list[dict[str, Any]]:
    """Return CreateWorkUnit payloads: one product WU per member plus integration."""
    ensemble_id = workspace.active_ensemble_id
    members = workspace.declared_members()
    if not ensemble_id or len(members) < 2:
        raise ValueError("an active ensemble with at least two members is required")
    payloads: list[dict[str, Any]] = []
    member_wu_ids: list[str] = []
    for entry in members:
        member_id = entry["id"]
        work_unit_id = f"WU-{ensemble_id}-{member_id}"
        member_wu_ids.append(work_unit_id)
        payloads.append(
            {
                "id": work_unit_id,
                "title": f"{ensemble_id} {member_id}",
                "member_id": member_id,
                "kind": "product",
                "objective": {
                    "result": f"Deliver the {member_id} change for ensemble {ensemble_id}."
                },
                "scope": {"include": ["."], "exclude": []},
                "expected_behavior": f"Member {member_id} remains independently releasable.",
                "acceptance_criteria": [f"member {member_id} verifies on its own Git"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": ["bounded member scope"]},
                "required_verification": {"unit_tests": True},
            }
        )
    payloads.append(
        {
            "id": f"WU-{ensemble_id}-integration",
            "kind": "integration",
            "title": f"{ensemble_id} integration",
            "objective": {
                "result": f"Integrate declared members of {ensemble_id} without writing product code."
            },
            "scope": {"include": [], "exclude": ["**"]},
            "expected_behavior": "No product file is written in any member Git.",
            "acceptance_criteria": [
                "no product write in a member repository",
                "depends on every member Work Unit",
            ],
            "dependencies": member_wu_ids,
            "risk": {"class": "medium", "reasons": ["cross-member integration"]},
            "required_verification": {"unit_tests": True},
        }
    )
    return payloads
