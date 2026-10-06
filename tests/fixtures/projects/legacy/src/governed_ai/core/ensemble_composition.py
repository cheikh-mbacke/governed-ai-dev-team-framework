"""Current composition pins, live HEAD checks, and frozen member checkouts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from governed_ai.core.orchestrator.git_workspace import (
    GitWorkspaceError,
    ensure_detached_worktree,
    head_sha,
)
from governed_ai.core.workspace import Workspace

PRODUCT_EVIDENCE_TYPES = frozenset({"e2e", "visual"})
PRODUCT_GATES = frozenset({"G3", "G4"})
COMPOSITIONS_DIR_NAME = "compositions"


def _raise(code: str, message: str, path: str = "/composition_id") -> None:
    from governed_ai.core.commands.errors import ErrorCode, GatewayError

    error_code = getattr(ErrorCode, code, ErrorCode.INVARIANT_VIOLATION)
    raise GatewayError(error_code, message, path)


def requires_product_composition(workspace: Workspace) -> bool:
    return len(workspace.declared_members()) >= 2


def current_composition_id(workspace: Workspace) -> str | None:
    path = workspace.ensemble_members_path
    if path is None or not path.is_file():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        return None
    value = document.get("current_composition")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_composition(workspace: Workspace, composition_id: str) -> dict[str, Any]:
    directory = workspace.ensemble_dir
    if directory is None:
        _raise(
            "INVARIANT_VIOLATION",
            "an active ensemble is required to load a composition",
            "/workspace",
        )
    path = directory / COMPOSITIONS_DIR_NAME / f"{composition_id}.yaml"
    if not path.is_file():
        _raise("NOT_FOUND", f"composition {composition_id!r} is not recorded")
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        _raise(
            "INVARIANT_VIOLATION",
            f"composition {composition_id!r} must be an object",
        )
    return document


def require_current_composition(workspace: Workspace) -> dict[str, Any]:
    """Return the current composition document when the ensemble has ≥2 members."""
    if not requires_product_composition(workspace):
        _raise(
            "INVARIANT_VIOLATION",
            "current composition is only required for ensembles with two or more members",
            "/workspace",
        )
    composition_id = current_composition_id(workspace)
    if not composition_id:
        _raise(
            "INVARIANT_VIOLATION",
            "a current composition_id is required for product gates, release "
            "candidates, and e2e evidence when the ensemble has two or more members",
        )
    return load_composition(workspace, composition_id)


def composition_head_mismatches(
    workspace: Workspace, composition: dict[str, Any]
) -> list[str]:
    """Return member ids whose live HEAD does not match the pinned SHA."""
    pins = composition.get("members") or {}
    if not isinstance(pins, dict):
        return ["<members>"]
    mismatched: list[str] = []
    declared = {entry["id"] for entry in workspace.declared_members()}
    for member_id in sorted(declared):
        pinned = pins.get(member_id)
        if not isinstance(pinned, str) or len(pinned) != 40:
            mismatched.append(member_id)
            continue
        try:
            live = head_sha(workspace.member_root(member_id))
        except GitWorkspaceError:
            mismatched.append(member_id)
            continue
        if live != pinned.lower():
            mismatched.append(member_id)
    extra = sorted(set(pins) - declared)
    mismatched.extend(extra)
    return mismatched


def assert_composition_live(
    workspace: Workspace, composition: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Reject product proof when a member HEAD has moved past the pin."""
    document = composition or require_current_composition(workspace)
    mismatched = composition_head_mismatches(workspace, document)
    if mismatched:
        _raise(
            "INVARIANT_VIOLATION",
            "composition is stale: member HEAD differs from the pinned SHA for "
            + ", ".join(mismatched)
            + "; re-pin and re-verify before e2e or G4",
        )
    return document


def ui_member_id(workspace: Workspace) -> str:
    members = workspace.declared_members()
    for entry in members:
        if entry.get("kind") == "ui":
            return str(entry["id"])
    for entry in members:
        if entry["id"] == "frontend":
            return str(entry["id"])
    if members:
        return str(members[0]["id"])
    _raise(
        "INVARIANT_VIOLATION",
        "ensemble has no members to freeze for visual verification",
        "/workspace",
    )
    raise AssertionError("unreachable")


def frozen_composition_checkout_path(
    workspace: Workspace, composition_id: str, member_id: str
) -> Path:
    ensemble_id = workspace.active_ensemble_id or "ensemble"
    return (
        workspace.instance_root
        / ".ai-team"
        / "worktrees"
        / ensemble_id
        / "compositions"
        / composition_id
        / member_id
    )


def ensure_frozen_composition_checkouts(
    workspace: Workspace, composition: dict[str, Any] | None = None
) -> dict[str, Path]:
    """Detach each member at its pinned SHA under the instance worktree home."""
    document = composition or require_current_composition(workspace)
    composition_id = str(document.get("id") or current_composition_id(workspace) or "")
    pins = document.get("members") or {}
    roots: dict[str, Path] = {}
    for entry in workspace.declared_members():
        member_id = entry["id"]
        sha = pins.get(member_id)
        if not isinstance(sha, str):
            _raise(
                "INVARIANT_VIOLATION",
                f"composition {composition_id!r} is missing a pin for member {member_id!r}",
            )
        checkout = frozen_composition_checkout_path(workspace, composition_id, member_id)
        try:
            roots[member_id] = ensure_detached_worktree(
                workspace.member_root(member_id), checkout, sha
            )
        except GitWorkspaceError as exc:
            _raise(
                "INVARIANT_VIOLATION",
                f"cannot freeze member {member_id!r} at {sha}: {exc}",
            )
    return roots


def enforce_product_gate_composition(workspace: Workspace, gate: str) -> dict[str, Any] | None:
    if gate not in PRODUCT_GATES or not requires_product_composition(workspace):
        return None
    document = require_current_composition(workspace)
    if gate == "G4":
        assert_composition_live(workspace, document)
    return document


def enforce_release_candidate_composition(
    workspace: Workspace, document: dict[str, Any]
) -> None:
    if not requires_product_composition(workspace):
        return
    composition = require_current_composition(workspace)
    composition_id = composition["id"]
    declared = document.get("composition_id")
    if declared is None:
        document["composition_id"] = composition_id
        return
    if declared != composition_id:
        _raise(
            "INVARIANT_VIOLATION",
            "release candidate composition_id must match the current composition "
            f"({declared!r} != {composition_id!r})",
            "/payload/composition_id",
        )


def enforce_product_evidence_composition(
    workspace: Workspace, payload: dict[str, Any]
) -> None:
    from governed_ai.core.code_revision import COMPOSITION, normalize_code_revision

    if not requires_product_composition(workspace):
        return
    evidence_type = str(payload.get("type") or "")
    try:
        revision = normalize_code_revision(payload.get("code_revision"))
    except (TypeError, ValueError) as exc:
        _raise("INVALID_SCHEMA", str(exc), "/payload/code_revision")
    if evidence_type not in PRODUCT_EVIDENCE_TYPES and (
        revision is None or revision.get("kind") != COMPOSITION
    ):
        return
    if revision is None or revision.get("kind") != COMPOSITION:
        _raise(
            "INVARIANT_VIOLATION",
            "e2e and visual evidence on a multi-member ensemble must use "
            "code_revision.kind composition",
            "/payload/code_revision",
        )
    composition = require_current_composition(workspace)
    composition_id = revision.get("composition_id")
    if composition_id != composition.get("id"):
        _raise(
            "INVARIANT_VIOLATION",
            "evidence composition_id must be the current composition "
            f"({composition_id!r} != {composition.get('id')!r})",
            "/payload/code_revision/composition_id",
        )
    cited = revision.get("members")
    pins = composition.get("members") or {}
    if cited is not None and dict(cited) != dict(pins):
        _raise(
            "INVARIANT_VIOLATION",
            "evidence composition member SHAs must match the pinned composition",
            "/payload/code_revision/members",
        )
    assert_composition_live(workspace, composition)
