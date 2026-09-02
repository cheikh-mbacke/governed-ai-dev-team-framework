"""IssueRunAuthorizationGrant command handler (Document 6 §8)."""

from __future__ import annotations

import hashlib
import json
from governed_ai.compat.datetime import UTC, datetime
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.contracts.bundle_hash import canonical_json_bytes
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.commands.run_authorization import REQUIRED_UNATTENDED_COMMANDS
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run.authorization_grant import MINIMUM_EXCLUDED_ACTIONS
from governed_ai.core.domain.run.autonomy_policy import (
    UNATTENDED_PRESETS,
    effective_policy_hash,
    resolve_effective_policy,
)
from governed_ai.core.domain.run.mission_artifact import (
    compute_artifact_hash,
    compute_mission_contract_hash,
    is_approved,
)
from governed_ai.core.persistence.transaction import Transaction


def _normalized_decision_menu(raw_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and initialize the grant's deterministic decision clauses."""
    decision_menu = []
    seen_entry_ids: set[str] = set()
    for index, raw_entry in enumerate(raw_entries):
        entry_id = raw_entry.get("id")
        if not entry_id:
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                "decision_menu entry.id is required",
                f"/payload/decision_menu/{index}/id",
            )
        if entry_id in seen_entry_ids:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"duplicate decision_menu entry id: {entry_id!r}",
                f"/payload/decision_menu/{index}/id",
            )
        seen_entry_ids.add(entry_id)
        entry = dict(raw_entry)
        entry.setdefault("scope", {})
        entry["uses_count"] = 0
        decision_menu.append(entry)
    return decision_menu


def handle_issue_run_authorization_grant(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    target = envelope["target"]
    grant_id = target["id"]
    payload = envelope["payload"]
    autonomy_preset = payload.get("autonomy_preset")

    human_authority = str((envelope.get("human_authorization") or {}).get("granted_by") or "")
    if human_authority and human_authority != str(payload.get("issuing_authority")):
        raise GatewayError(
            ErrorCode.UNAUTHORIZED,
            "issuing_authority must match human_authorization.granted_by",
            "/payload/issuing_authority",
        )

    grant_path = workspace_root.ai_team / "run-authorization-grants" / f"{grant_id}.json"
    if grant_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"run authorization grant {grant_id!r} already exists",
            "/target/id",
        )

    excluded_actions = set(payload.get("excluded_actions") or [])
    if not MINIMUM_EXCLUDED_ACTIONS.issubset(excluded_actions):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"excluded_actions must include at least {sorted(MINIMUM_EXCLUDED_ACTIONS)}",
            "/payload/excluded_actions",
        )

    # Document 6 §5.2 — every entry is typed and machine-verifiable, never free text.
    decision_menu = _normalized_decision_menu(payload.get("decision_menu") or [])

    # Document 6 §6.2/§8 — an artifact can only back a grant once it has
    # survived an independent adversarial review; the Core checks this from
    # the artifact's own recorded state, never from the grant author's say-so.
    mission_artifact_ids = payload.get("mission_artifact_ids") or []
    mission_artifacts: list[dict[str, Any]] = []
    for artifact_id in mission_artifact_ids:
        artifact_path = workspace_root.ai_team / "mission-artifacts" / f"{artifact_id}.json"
        if not artifact_path.is_file():
            raise GatewayError(
                ErrorCode.NOT_FOUND,
                f"mission artifact {artifact_id!r} not found",
                "/payload/mission_artifact_ids",
            )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        # Document 6 §6.2 starts the independent challenger at extended+.
        # Conservative may attach pending artifacts (human auth on this command
        # is enough). Any other preset — and grants without a preset that still
        # bind mission artifacts — must only consume independently approved ones.
        challenge_required = autonomy_preset != "unattended_conservative"
        if challenge_required and not is_approved(artifact):
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"mission artifact {artifact_id!r} has not been approved by an "
                "independent challenge",
                "/payload/mission_artifact_ids",
            )
        mission_artifacts.append(artifact)

    decision_artifact = next(
        (artifact for artifact in mission_artifacts if artifact.get("kind") == "decision_menu"),
        None,
    )
    if decision_artifact is not None:
        artifact_entries = (decision_artifact.get("content") or {}).get("entries") or []
        supplied_entries = payload.get("decision_menu")
        if supplied_entries is not None and supplied_entries != artifact_entries:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "grant decision_menu differs from the approved decision-menu artifact",
                "/payload/decision_menu",
            )
        decision_menu = _normalized_decision_menu(artifact_entries)

    execution_artifact = next(
        (
            artifact
            for artifact in mission_artifacts
            if artifact.get("kind") == "execution_envelope"
        ),
        None,
    )
    if execution_artifact is not None:
        execution_content = execution_artifact.get("content") or {}
        artifact_ceilings = execution_content.get("execution_ceilings_by_work_unit") or {}
        missing_ceilings = sorted(set(payload["work_unit_ids"]) - set(artifact_ceilings))
        if missing_ceilings:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"execution envelope has no ceiling for work units: {missing_ceilings}",
                "/payload/mission_artifact_ids",
            )
        artifact_environments = set(execution_content.get("environments") or [])
        supplied_environments = set(payload.get("allowed_environments") or [])
        if autonomy_preset is not None and supplied_environments != artifact_environments:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "grant allowed_environments must exactly match the execution-envelope artifact",
                "/payload/allowed_environments",
            )

    effective_policy = None
    policy_hash = None
    if autonomy_preset is not None:
        if autonomy_preset not in UNATTENDED_PRESETS:
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"unsupported unattended preset {autonomy_preset!r}",
                "/payload/autonomy_preset",
            )
        try:
            effective_policy = resolve_effective_policy(
                autonomy_preset,
                overrides=payload.get("effective_autonomy_policy_overrides"),
            )
        except ValueError as exc:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                str(exc),
                "/payload/effective_autonomy_policy_overrides",
            ) from exc
        policy_hash = effective_policy_hash(effective_policy)
        allowed_environments = set(payload.get("allowed_environments") or [])
        if not allowed_environments or allowed_environments - {"development", "test"}:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "unattended grants must explicitly allow only development/test environments",
                "/payload/allowed_environments",
            )
        if not payload.get("allowed_commands"):
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "unattended grants require an explicit non-empty command allowlist",
                "/payload/allowed_commands",
            )
        required_commands = set(REQUIRED_UNATTENDED_COMMANDS)
        if autonomy_preset in {"unattended_extended", "unattended_maximal", "custom"}:
            required_commands.add("RecordIntegrationMerge")
        if autonomy_preset in {"unattended_maximal", "custom"}:
            required_commands.add("RegisterReleaseCandidate")
        missing_commands = sorted(required_commands - set(payload["allowed_commands"]))
        if missing_commands:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                f"unattended grant is missing required Core commands: {missing_commands}",
                "/payload/allowed_commands",
            )
        maximum_duration = payload.get("maximum_duration_hours")
        if maximum_duration is None or maximum_duration <= 0:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "unattended grants require a positive maximum_duration_hours",
                "/payload/maximum_duration_hours",
            )
        if payload.get("maximum_spend") is None and payload.get("maximum_tokens") is None:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "unattended grants require maximum_spend or maximum_tokens",
                "/payload/maximum_spend",
            )

    now = datetime.now(UTC).isoformat()
    document = {
        "id": grant_id,
        "revision": 1,
        "issued_at": now,
        "issuing_authority": payload["issuing_authority"],
        "work_unit_ids": payload["work_unit_ids"],
        "allowed_commands": payload.get("allowed_commands", []),
        "allowed_environments": payload.get("allowed_environments", []),
        "allowed_shell_commands": (
            list((execution_artifact.get("content") or {}).get("allowed_commands") or [])
            if execution_artifact is not None
            else []
        ),
        "allowed_paths": (
            list((execution_artifact.get("content") or {}).get("allowed_paths") or [])
            if execution_artifact is not None
            else []
        ),
        "accessible_secrets": (
            list((execution_artifact.get("content") or {}).get("accessible_secrets") or [])
            if execution_artifact is not None
            else []
        ),
        "maximum_spend": payload.get("maximum_spend"),
        "maximum_duration_hours": payload.get("maximum_duration_hours"),
        "maximum_tokens": payload.get("maximum_tokens"),
        "spend_used": 0.0,
        "tokens_used": 0,
        "expires_at": payload["expires_at"],
        "maximum_uses": payload["maximum_uses"],
        "uses_count": 0,
        "excluded_actions": sorted(excluded_actions),
        "revoked_at": None,
        "revoked_reason": None,
        "decision_menu": decision_menu,
        "decision_menu_version": (
            "sha256:" + hashlib.sha256(canonical_json_bytes(decision_menu)).hexdigest()
        ),
        "mission_artifact_ids": mission_artifact_ids,
        "mission_contract_hash": (
            compute_mission_contract_hash(mission_artifacts) if mission_artifacts else None
        ),
        "mission_artifact_hashes": {
            artifact["id"]: compute_artifact_hash(artifact) for artifact in mission_artifacts
        },
        "autonomy_preset": autonomy_preset,
        "effective_autonomy_policy": effective_policy,
        "effective_autonomy_policy_hash": policy_hash,
    }
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "run-authorization-grant.schema.json",
        root_path="",
    )
    transaction.plan_json_write(grant_path, document)
    consume_human_authorization(
        envelope, workspace_ai_team=workspace_root.ai_team, transaction=transaction
    )

    return {
        "affected": [{"kind": "run_authorization_grant", "id": grant_id, "revision": 1}],
    }, []
