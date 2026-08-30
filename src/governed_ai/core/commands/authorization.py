"""Role authorization against the active Published Contract Bundle."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from governed_ai.contracts.compatibility import resolve_active_bundle_dir
from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.run_authorization import authorize_run_grant

# Commands granted beyond bundle writes (findings, release prep, evidence from implementers).
SUPPLEMENTAL_ROLE_COMMANDS: dict[str, frozenset[str]] = {
    "control-plane": frozenset(
        {
            "ResolveDecisionRequest",
            "RecordGateDecision",
            "RecordAcceptance",
            "ExportFeedback",
            # Document 6 §10.2 — run-reliability-controller is a mechanical Core
            # component, not a distinct judgment-bearing role; it is exercised
            # through the control-plane actor identity.
            "OpenRun",
            "AcquireWorkerLease",
            "RecordExecutionAttempt",
            "WriteCheckpoint",
            "CloseRun",
            # Document 6 §8 — grant issuance/revocation is a human-gated act,
            # exercised through the control-plane actor identity.
            "IssueRunAuthorizationGrant",
            "RevokeRunAuthorizationGrant",
            # Document 6 §5.3/§10.1 — mandate-matcher only *proposes*; the
            # deterministic validation happens in the handler, never in the
            # actor issuing the command. Exercised through control-plane
            # pending a dedicated, adapter-compiled mandate-matcher role.
            "ResolveRunDecision",
            # Document 6 §7.3 — escalation only; the Core enforces the
            # one-way ratchet, not the actor requesting it.
            "TightenExecutionCeiling",
            # Document 6 §9.8 — integration-steward supervises the merge
            # queue; the Core enforces the bounded conflict-resolution limit
            # and the mandatory revalidation, not the actor recording it.
            # Exercised through control-plane pending a dedicated,
            # adapter-compiled integration-steward role.
            "RecordIntegrationMerge",
            # Orchestrator prerequisite — heartbeat refresh is mechanical
            # bookkeeping, fencing-checked by the handler, not a judgment call.
            "RecordWorkerHeartbeat",
            "ReleaseWorkerLease",
        }
    ),
    "backend-developer": frozenset({"RegisterEvidence"}),
    "qa-test": frozenset({"RegisterEvidence"}),
    # Document 6 §6.2 — the auditor is the independent reviewer of mission
    # artifacts precisely because it is never the role that drafts them; no
    # new "requirements-challenger" identity is needed to get that
    # separation, since the Core checks actor role_id != authored_by_role.
    "auditor": frozenset({"RegisterFinding", "RecordMissionArtifactChallenge"}),
    "code-reviewer": frozenset({"RegisterFinding"}),
    "security-reviewer": frozenset({"RegisterFinding"}),
    "release-agent": frozenset({"RegisterReleaseCandidate"}),
    # Document 6 §6.1 — the Product Analyst drafts mission artifacts.
    "product-analyst": frozenset({"RegisterMissionArtifact"}),
}


@lru_cache(maxsize=8)
def _load_role_ids(bundle_dir: str) -> frozenset[str]:
    roles_path = Path(bundle_dir) / "roles"
    role_ids: set[str] = set()
    for path in roles_path.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        role_ids.add(doc["role_id"])
    return frozenset(role_ids)


@lru_cache(maxsize=32)
def _allowed_commands_for_role(bundle_dir: str, role_id: str) -> frozenset[str]:
    role_path = Path(bundle_dir) / "roles" / f"{role_id}.json"
    doc = json.loads(role_path.read_text(encoding="utf-8"))
    allowed = set(doc["writes"]["authoritative_governance_commands"])
    allowed.update(doc["writes"]["non_authoritative_signal_commands"])
    allowed.update(SUPPLEMENTAL_ROLE_COMMANDS.get(role_id, frozenset()))
    return frozenset(allowed)


def authorize_command(envelope: dict[str, Any], workspace_ai_team: Path) -> None:
    actor = envelope["actor"]
    role_id = actor["role_id"]
    command_type = envelope["type"]

    try:
        bundle_dir = resolve_active_bundle_dir(workspace_ai_team / "contracts")
    except Exception as exc:
        raise GatewayError(
            ErrorCode.UNSUPPORTED_CONTRACT,
            f"active bundle unavailable: {exc}",
            "/actor/bundle_version",
        ) from exc

    known_roles = _load_role_ids(str(bundle_dir))
    if role_id not in known_roles:
        raise GatewayError(ErrorCode.UNAUTHORIZED, f"unknown role {role_id!r}", "/actor/role_id")

    allowed = _allowed_commands_for_role(str(bundle_dir), role_id)
    if command_type not in allowed:
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            f"role {role_id!r} cannot invoke {command_type!r}",
            "/type",
        )

    # Document 6 §8 — mechanical Core check, shared choke point, cannot be
    # bypassed by any handler.
    authorize_run_grant(envelope, workspace_ai_team)

    if envelope.get("human_authorization"):
        auth = envelope["human_authorization"]
        auth_id = auth.get("authorization_id")
        if not auth_id:
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                "human_authorization.authorization_id required",
                "/human_authorization/authorization_id",
            )
        consumed_path = workspace_ai_team / "authorizations" / f"{auth_id}.json"
        if consumed_path.is_file():
            record = json.loads(consumed_path.read_text(encoding="utf-8"))
            if record.get("consumed_at"):
                raise GatewayError(
                    ErrorCode.UNAUTHORIZED,
                    "human authorization already consumed",
                    "/human_authorization/authorization_id",
                )
