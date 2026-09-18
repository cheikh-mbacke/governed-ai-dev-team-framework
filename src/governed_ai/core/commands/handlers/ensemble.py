"""Ensemble / member / composition commands (Document 25 Phase 3)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.commands.validation import validate_against_schema
from governed_ai.core.member_overlay import write_member_overlay
from governed_ai.core.orchestrator.git_workspace import GitWorkspaceError, head_sha
from governed_ai.core.persistence.transaction import Transaction
from governed_ai.core.workspace import MEMBERS_FILE_NAME, Workspace
from governed_ai.core.workspace_mode import (
    CLIENT_CYCLE_FORBIDDEN_MESSAGE,
    is_framework_source,
)

ENSEMBLE_ID_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
COMPOSITION_ID_RE = re.compile(r"^CR-[A-Za-z0-9._-]+$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
ACTIVE_ENSEMBLE_FILE = "active-ensemble.yaml"
COMPOSITIONS_DIR_NAME = "compositions"

_DEFAULT_GATES = {
    "G0": {"status": "not_required"},
    "G1": {"status": "not_required"},
    "G2": {"status": "not_required"},
    "G3": {"status": "not_required"},
    "G4": {"status": "not_required"},
}


def _reject_framework_source(workspace: Workspace) -> None:
    if is_framework_source(workspace):
        raise GatewayError(
            ErrorCode.UNSUPPORTED_CONTRACT,
            CLIENT_CYCLE_FORBIDDEN_MESSAGE,
            "/workspace",
        )


def _instance_id(workspace: Workspace) -> str:
    path = workspace.profile_path
    if not path.is_file():
        raise GatewayError(ErrorCode.NOT_FOUND, "project profile not found", "/workspace")
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise GatewayError(ErrorCode.INVARIANT_VIOLATION, "project profile must be an object", "/workspace")
    project = document.get("project")
    value = project.get("id") if isinstance(project, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise GatewayError(ErrorCode.INVARIANT_VIOLATION, "project.id is required", "/workspace")
    return value.strip()


def _require_ensemble_id(value: Any, pointer: str) -> str:
    if not isinstance(value, str) or not ENSEMBLE_ID_RE.fullmatch(value):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "ensemble id must match ^[a-z][a-z0-9._-]*$",
            pointer,
        )
    return value


def _members_path(workspace: Workspace, ensemble_id: str) -> Path:
    return workspace.ensembles_root / ensemble_id / MEMBERS_FILE_NAME


def _load_members_document(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "ensemble members document must be an object",
            "/target/id",
        )
    return document


def _require_members(workspace: Workspace, ensemble_id: str) -> dict[str, Any]:
    document = _load_members_document(_members_path(workspace, ensemble_id))
    if document is None:
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"ensemble {ensemble_id!r} is not registered",
            "/target/id",
        )
    return document


def _check_expected_revision(target: dict[str, Any], current: int) -> None:
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    expected = target["expected_revision"]
    if expected != current:
        raise GatewayError(
            ErrorCode.CONFLICT,
            f"expected revision {expected}, found {current}",
            "/target/expected_revision",
        )


def _is_git_repository(path: Path) -> bool:
    git = path / ".git"
    return git.is_dir() or git.is_file()


def _catalog_entry(ensemble_id: str, members_doc: dict[str, Any]) -> dict[str, Any]:
    member_ids = [
        entry["id"]
        for entry in members_doc.get("members") or []
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]
    entry: dict[str, Any] = {
        "id": ensemble_id,
        "status": str(members_doc.get("status") or "registered"),
        "members": member_ids,
    }
    composition = members_doc.get("current_composition")
    if isinstance(composition, str) and composition:
        entry["composition"] = composition
    return entry


def _project_catalog(
    workspace: Workspace,
    transaction: Transaction,
    *,
    updated_ensemble_id: str,
    updated_members_doc: dict[str, Any],
) -> None:
    ensembles: list[dict[str, Any]] = []
    seen: set[str] = set()
    root = workspace.ensembles_root
    if root.is_dir():
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            if directory.name == updated_ensemble_id:
                entry = _catalog_entry(directory.name, updated_members_doc)
            else:
                existing = _load_members_document(directory / MEMBERS_FILE_NAME)
                if existing is None:
                    continue
                entry = _catalog_entry(directory.name, existing)
            ensembles.append(entry)
            seen.add(directory.name)
    if updated_ensemble_id not in seen:
        ensembles.append(_catalog_entry(updated_ensemble_id, updated_members_doc))
        ensembles.sort(key=lambda item: item["id"])
    catalog = {
        "schema_version": 1,
        "instance_id": _instance_id(workspace),
        "ensembles": ensembles,
    }
    validate_against_schema(
        workspace.ai_team,
        catalog,
        "catalog.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(workspace.catalog_path, catalog)


def _empty_project_state(ensemble_id: str) -> dict[str, Any]:
    return {
        "project_id": ensemble_id,
        "constitution_version": "1.4.0",
        "phase": "not_compiled",
        "gates": dict(_DEFAULT_GATES),
        "work_units": {},
        "dependency_edges": [],
        "active_workers": [],
        "open_decisions": [],
        "open_blockers": [],
        "open_defects": [],
        "open_findings": [],
        "last_updated": datetime.now(UTC).isoformat(),
    }


def handle_register_ensemble(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    _reject_framework_source(workspace_root)
    ensemble_id = _require_ensemble_id(envelope["target"]["id"], "/target/id")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    payload_id = payload.get("id")
    if payload_id != ensemble_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )
    members_path = _members_path(workspace_root, ensemble_id)
    if members_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"ensemble {ensemble_id!r} already exists",
            "/target/id",
        )
    now = datetime.now(UTC).isoformat()
    name = payload.get("name") if isinstance(payload.get("name"), str) else ensemble_id
    docs_path = payload.get("docs_path")
    members_doc: dict[str, Any] = {
        "ensemble_id": ensemble_id,
        "status": "registered",
        "revision": 1,
        "members": [],
        "created_at": now,
        "updated_at": now,
    }
    if isinstance(docs_path, str) and docs_path.strip():
        members_doc["docs_path"] = docs_path.strip()
    validate_against_schema(
        workspace_root.ai_team,
        members_doc,
        "ensemble-members.schema.json",
        root_path="",
    )
    profile = {
        "project": {
            "id": ensemble_id,
            "name": name,
        }
    }
    state = _empty_project_state(ensemble_id)
    ensemble_dir = workspace_root.ensembles_root / ensemble_id
    transaction.plan_yaml_write(members_path, members_doc)
    transaction.plan_yaml_write(ensemble_dir / "project-profile.yaml", profile)
    transaction.plan_yaml_write(ensemble_dir / "state" / "project-state.yaml", state)
    _project_catalog(
        workspace_root,
        transaction,
        updated_ensemble_id=ensemble_id,
        updated_members_doc=members_doc,
    )
    return {
        "affected": [
            {"kind": "ensemble", "id": ensemble_id, "revision": 1, "status": "registered"}
        ]
    }, []


def handle_register_member(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    _reject_framework_source(workspace_root)
    ensemble_id = _require_ensemble_id(envelope["target"]["id"], "/target/id")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    member_id = payload.get("id")
    if not isinstance(member_id, str) or not ENSEMBLE_ID_RE.fullmatch(member_id):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match ^[a-z][a-z0-9._-]*$",
            "/payload/id",
        )
    kind = payload.get("kind")
    raw_path = payload.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.path is required", "/payload/path")

    members_path = _members_path(workspace_root, ensemble_id)
    members_doc = _require_members(workspace_root, ensemble_id)
    current_revision = int(members_doc.get("revision") or 1)
    _check_expected_revision(envelope["target"], current_revision)

    existing_ids = {
        entry.get("id")
        for entry in members_doc.get("members") or []
        if isinstance(entry, dict)
    }
    if member_id in existing_ids:
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"member {member_id!r} already exists in ensemble {ensemble_id!r}",
            "/payload/id",
        )

    resolved = Path(raw_path)
    if not resolved.is_absolute():
        resolved = (workspace_root.instance_root / resolved).resolve()
    else:
        resolved = resolved.resolve()
    if not resolved.is_dir():
        raise GatewayError(
            ErrorCode.NOT_FOUND,
            f"member path {raw_path!r} is not a directory",
            "/payload/path",
        )
    if resolved == workspace_root.instance_root:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "hors-arbre member path must not equal the instance root",
            "/payload/path",
        )
    if not _is_git_repository(resolved):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "member path must be a local Git repository",
            "/payload/path",
        )

    entry: dict[str, Any] = {
        "id": member_id,
        "kind": kind,
        "path": raw_path.strip(),
    }
    origin = payload.get("origin")
    if isinstance(origin, str) and origin.strip():
        entry["origin"] = origin.strip()
    source_roots = payload.get("source_roots")
    if isinstance(source_roots, list):
        entry["source_roots"] = source_roots
    commands = payload.get("commands")
    if isinstance(commands, dict):
        entry["commands"] = commands

    members_list = list(members_doc.get("members") or [])
    members_list.append(entry)
    now = datetime.now(UTC).isoformat()
    updated = dict(members_doc)
    updated["members"] = members_list
    updated["revision"] = current_revision + 1
    updated["updated_at"] = now
    validate_against_schema(
        workspace_root.ai_team,
        updated,
        "ensemble-members.schema.json",
        root_path="",
    )
    transaction.plan_yaml_write(members_path, updated)
    _project_catalog(
        workspace_root,
        transaction,
        updated_ensemble_id=ensemble_id,
        updated_members_doc=updated,
    )
    link_document = {
        "schema_version": 1,
        "instance_id": _instance_id(workspace_root),
        "ensemble_id": ensemble_id,
        "member_id": member_id,
        "instance_path": str(workspace_root.instance_root),
    }
    validate_against_schema(
        workspace_root.ai_team,
        link_document,
        "member-link.schema.json",
        root_path="",
    )
    write_member_overlay(
        resolved,
        instance_id=link_document["instance_id"],
        ensemble_id=ensemble_id,
        member_id=member_id,
        instance_path=workspace_root.instance_root,
    )
    return {
        "affected": [
            {
                "kind": "ensemble_member",
                "id": member_id,
                "ensemble_id": ensemble_id,
                "revision": updated["revision"],
            }
        ]
    }, []


def handle_pin_composition(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    _reject_framework_source(workspace_root)
    composition_id = envelope["target"]["id"]
    if not isinstance(composition_id, str) or not COMPOSITION_ID_RE.fullmatch(composition_id):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "target.id must match ^CR-[A-Za-z0-9._-]+$",
            "/target/id",
        )
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    if payload.get("id") != composition_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.id must match target.id",
            "/payload/id",
        )
    ensemble_id = payload.get("ensemble_id")
    if not isinstance(ensemble_id, str):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.ensemble_id is required",
            "/payload/ensemble_id",
        )
    ensemble_id = _require_ensemble_id(ensemble_id, "/payload/ensemble_id")
    members_path = _members_path(workspace_root, ensemble_id)
    members_doc = _require_members(workspace_root, ensemble_id)
    declared = [
        entry
        for entry in members_doc.get("members") or []
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]
    if not declared:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "cannot pin a composition on an ensemble with no members",
            "/payload/ensemble_id",
        )

    cr_path = (
        workspace_root.ensembles_root / ensemble_id / COMPOSITIONS_DIR_NAME / f"{composition_id}.yaml"
    )
    if cr_path.is_file():
        raise GatewayError(
            ErrorCode.ALREADY_EXISTS,
            f"composition {composition_id!r} already exists",
            "/target/id",
        )

    explicit = payload.get("members")
    member_shas: dict[str, str] = {}
    if explicit is None:
        for entry in declared:
            member_id = entry["id"]
            raw_path = entry.get("path")
            if not isinstance(raw_path, str):
                raise GatewayError(
                    ErrorCode.INVARIANT_VIOLATION,
                    f"member {member_id!r} is missing path",
                    "/payload/members",
                )
            resolved = Path(raw_path)
            if not resolved.is_absolute():
                resolved = (workspace_root.instance_root / resolved).resolve()
            else:
                resolved = resolved.resolve()
            try:
                member_shas[member_id] = head_sha(resolved)
            except GitWorkspaceError as exc:
                raise GatewayError(
                    ErrorCode.INVARIANT_VIOLATION,
                    f"cannot read HEAD for member {member_id!r}: {exc}",
                    "/payload/members",
                ) from exc
    elif isinstance(explicit, dict):
        declared_ids = {entry["id"] for entry in declared}
        extra = sorted(set(explicit) - declared_ids)
        missing = sorted(declared_ids - set(explicit))
        if extra or missing:
            raise GatewayError(
                ErrorCode.INVARIANT_VIOLATION,
                "payload.members must cover exactly the declared ensemble members",
                "/payload/members",
            )
        for member_id, sha in explicit.items():
            if not isinstance(member_id, str) or not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                raise GatewayError(
                    ErrorCode.INVALID_SCHEMA,
                    "each composition SHA must be 40 lowercase hex characters",
                    "/payload/members",
                )
            member_shas[member_id] = sha
    else:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.members must be an object when provided",
            "/payload/members",
        )

    now = datetime.now(UTC).isoformat()
    document = {
        "id": composition_id,
        "ensemble_id": ensemble_id,
        "kind": "composition",
        "members": member_shas,
        "created_at": now,
    }
    validate_against_schema(
        workspace_root.ai_team,
        document,
        "composition-revision.schema.json",
        root_path="",
    )
    updated = dict(members_doc)
    updated["current_composition"] = composition_id
    updated["updated_at"] = now
    transaction.plan_yaml_write(cr_path, document)
    transaction.plan_yaml_write(members_path, updated)
    _project_catalog(
        workspace_root,
        transaction,
        updated_ensemble_id=ensemble_id,
        updated_members_doc=updated,
    )
    return {
        "affected": [
            {
                "kind": "composition",
                "id": composition_id,
                "ensemble_id": ensemble_id,
            }
        ]
    }, []


def handle_set_active_ensemble(
    envelope: dict[str, Any],
    *,
    workspace_root,
    transaction: Transaction,
) -> tuple[dict[str, Any], list[str]]:
    _reject_framework_source(workspace_root)
    ensemble_id = _require_ensemble_id(envelope["target"]["id"], "/target/id")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    payload_id = payload.get("ensemble_id", ensemble_id)
    if payload_id != ensemble_id:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            "payload.ensemble_id must match target.id",
            "/payload/ensemble_id",
        )
    _require_members(workspace_root, ensemble_id)
    document = {"ensemble_id": ensemble_id, "updated_at": datetime.now(UTC).isoformat()}
    transaction.plan_yaml_write(
        workspace_root.ai_team / ACTIVE_ENSEMBLE_FILE,
        document,
    )
    return {"affected": [{"kind": "active_ensemble", "id": ensemble_id}]}, []
