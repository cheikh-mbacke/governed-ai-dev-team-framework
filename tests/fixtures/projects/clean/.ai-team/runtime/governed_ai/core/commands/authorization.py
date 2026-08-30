"""Role authorization against the active Published Contract Bundle."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from governed_ai.contracts.compatibility import resolve_active_bundle_dir
from governed_ai.core.commands.errors import ErrorCode, GatewayError

# Commands granted beyond bundle writes (findings, release prep, evidence from implementers).
SUPPLEMENTAL_ROLE_COMMANDS: dict[str, frozenset[str]] = {
    "control-plane": frozenset(
        {"ResolveDecisionRequest", "RecordGateDecision", "RecordAcceptance", "ExportFeedback"}
    ),
    "backend-developer": frozenset({"RegisterEvidence"}),
    "qa-test": frozenset({"RegisterEvidence"}),
    "auditor": frozenset({"RegisterFinding"}),
    "code-reviewer": frozenset({"RegisterFinding"}),
    "security-reviewer": frozenset({"RegisterFinding"}),
    "release-agent": frozenset({"RegisterReleaseCandidate"}),
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
