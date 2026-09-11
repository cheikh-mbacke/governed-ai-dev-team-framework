"""Governed, auditable updates to the installed Project Profile."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.human_authorization import consume_human_authorization
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.domain.run.autonomy_policy import resolve_project_preset
from governed_ai.core.persistence.transaction import Transaction

MUTABLE_SECTIONS = frozenset(
    {
        "autonomy",
        "commands",
        "communication",
        "human_authorities",
        "notifications",
        "paths",
        "release",
        "runtime_environments",
    }
)


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def handle_update_project_profile(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    profile_path = workspace_root.ai_team / "project-profile.yaml"
    if not profile_path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, "project profile not found", "/target/id")

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    target = envelope["target"]
    project_id = str((profile.get("project") or {}).get("id") or "")
    if target["id"] != project_id:
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"project profile {target['id']!r} not found",
            "/target/id",
        )

    current_revision = int(profile.get("config_revision", 1))
    if target["expected_revision"] != current_revision:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {target['expected_revision']}, found {current_revision}",
            "/target/expected_revision",
        )

    changes = envelope["payload"]["changes"]
    unsupported = sorted(set(changes) - MUTABLE_SECTIONS)
    if unsupported:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "these Project Profile sections are immutable through this command: "
            + ", ".join(unsupported),
            "/payload/changes",
        )

    updated = _merge(profile, changes)
    autonomy_patch = changes.get("autonomy")
    # Named preset in the patch replaces legacy level (configure.py autonomy path).
    if (
        isinstance(autonomy_patch, dict)
        and autonomy_patch.get("preset") is not None
        and isinstance(updated.get("autonomy"), dict)
    ):
        updated["autonomy"].pop("level", None)
    try:
        autonomy_block = updated.get("autonomy") or {}
        if not isinstance(autonomy_block, dict):
            raise ValueError("autonomy must be an object")
        resolved_preset = resolve_project_preset(autonomy_block)
    except ValueError as exc:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION, str(exc), "/payload/changes/autonomy"
        ) from exc

    # Durable migration: once a named preset is present, drop legacy level.
    if isinstance(updated.get("autonomy"), dict) and updated["autonomy"].get("preset"):
        updated["autonomy"].pop("level", None)

    now = datetime.now(UTC)
    updated["config_revision"] = current_revision + 1
    updated["updated_at"] = now.isoformat()
    validate_against_schema(
        workspace_root.ai_team,
        updated,
        "project-profile.schema.json",
        root_path="",
    )

    change_id = f"PROFILE-CHANGE-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    change_document = {
        "id": change_id,
        "project_id": project_id,
        "previous_revision": current_revision,
        "new_revision": current_revision + 1,
        "changes": changes,
        "reason": envelope["payload"]["reason"],
        "changed_by": envelope["human_authorization"].get("granted_by"),
        "changed_at": now.isoformat(),
        "effective_scope": "future_runs",
        "resolved_autonomy_preset": resolved_preset,
    }
    validate_against_schema(
        workspace_root.ai_team,
        change_document,
        "project-profile-change.schema.json",
        root_path="",
    )

    consume_human_authorization(
        envelope,
        workspace_ai_team=workspace_root.ai_team,
        transaction=transaction,
    )
    transaction.plan_yaml_write(profile_path, updated)
    transaction.plan_yaml_write(
        workspace_root.ai_team / "profile-changes" / f"{change_id}.yaml",
        change_document,
    )
    return {
        "affected": [
            {
                "kind": "project_profile",
                "id": project_id,
                "revision": current_revision + 1,
            }
        ],
        "details": {
            "change_id": change_id,
            "effective_scope": "future_runs",
            "autonomy_preset": resolved_preset,
        },
    }, [change_id]
