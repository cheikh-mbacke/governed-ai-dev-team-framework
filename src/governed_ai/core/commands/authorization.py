"""Role authorization against the active Published Contract Bundle."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from governed_ai.contracts.compatibility import resolve_active_bundle_dir
from governed_ai.core.commands.errors import ErrorCode, GatewayError

CONTROL_PLANE_ROLE = "control-plane"

ROLE_COMMANDS: dict[str, frozenset[str]] = {
    CONTROL_PLANE_ROLE: frozenset(
        {
            "CreateWorkUnit",
            "TransitionWorkUnit",
            "RegisterEvidence",
            "CreateDecisionRequest",
            "TransitionObservation",
            "GenerateRetrospective",
        }
    ),
    "backend-developer": frozenset({"RegisterEvidence", "RecordObservation"}),
    "qa-test": frozenset({"RegisterEvidence", "RecordObservation"}),
    "auditor": frozenset({"RegisterFinding", "RecordObservation"}),
    "code-reviewer": frozenset({"RegisterFinding", "RecordObservation"}),
    "security-reviewer": frozenset({"RegisterFinding", "RecordObservation"}),
    "release-agent": frozenset({"RegisterReleaseCandidate", "RecordObservation"}),
}


@lru_cache(maxsize=8)
def _load_role_ids(bundle_dir: str) -> frozenset[str]:
    roles_path = Path(bundle_dir) / "roles"
    role_ids: set[str] = set()
    for path in roles_path.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        role_ids.add(doc["role_id"])
    return frozenset(role_ids)


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

    allowed = ROLE_COMMANDS.get(role_id, frozenset())
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
